/* global messenger, browser */
/**
 * Canary Thunderbird add-on: connect, sign in, linked matter (Message-ID), file raw .eml, native “Canary” message tag.
 */
;(function () {
  'use strict'

  /** Thunderbird MessageId is an integer (TB 128+); strings break messages.get/getRaw. */
  function normalizeMessageId(id) {
    if (id == null) return null
    if (typeof id === 'number' && !Number.isNaN(id)) return id
    const n = parseInt(String(id), 10)
    return Number.isFinite(n) ? n : null
  }

  let search = ''
  let isCompanion = false
  /** @type {true|null|number} */
  let contextFilingMessageId = null
  try {
    search = String((globalThis.location && globalThis.location.search) || '')
  } catch {
    search = ''
  }
  isCompanion = search.indexOf('companion=1') !== -1
  if (search.indexOf('contextFiling=1') !== -1) {
    contextFilingMessageId = true
    try {
      const params = new URLSearchParams(search)
      const mid = normalizeMessageId(params.get('messageId'))
      if (mid != null) contextFilingMessageId = mid
    } catch (_) {
      /* keep true */
    }
  }
  if (search.indexOf('canaryDock=1') !== -1) {
    if (globalThis.document && globalThis.document.documentElement) {
      globalThis.document.documentElement.classList.add('canary-dock')
    }
  }
  if (isCompanion) {
    if (globalThis.document && globalThis.document.documentElement) {
      globalThis.document.documentElement.classList.add('canary-companion')
    }
  }

  const ORIGIN_KEY = 'canaryApiOrigin'
  const JWT_KEY = 'canary_jwt'
  /** @type {Array<{ id: unknown, case_number?: unknown, client_name?: unknown, matter_description?: unknown }>} */
  let allCases = []
  let selectedCaseId = ''
  let linkedCaseId = ''
  /** Last message id we refreshed the filing banner for (context filing reuses one window). */
  let contextFilingLoadedForMessageId = null
  /** If true, user opened “Server & sign-in” while a session is valid. When not signed in, the server block is always shown. */
  let settingsOpen = false

  function getExt() {
    return globalThis.messenger || globalThis.browser
  }

  function $(id) {
    return document.getElementById(id)
  }

  function out(el, text, asError) {
    if (!el) return
    el.classList.remove('ok', 'err', 'busy')
    if (asError === 'busy') {
      el.classList.add('busy')
    } else if (text) {
      el.classList.add(asError ? 'err' : 'ok')
    }
    el.textContent = text || ''
  }

  function setLinkedCaseLineEl(el, { text, state }) {
    if (!el) return
    el.classList.remove('is-ok', 'is-warn', 'is-muted')
    if (state === 'ok') el.classList.add('is-ok')
    else if (state === 'warn') el.classList.add('is-warn')
    else if (state === 'muted') el.classList.add('is-muted')
    el.textContent = text || ''
  }

  function setSubhead(mode) {
    const el = $('subhead')
    if (!el) return
    el.classList.remove('subhead--filing', 'subhead--server')
    if (mode === 'filing') {
      el.classList.add('subhead--filing')
      el.textContent = 'Select a matter and file. Use “Server & sign-in” only to change site or account.'
    } else {
      el.classList.add('subhead--server')
      el.textContent = 'Set your Canary site and sign in here. When done, the filing view opens automatically.'
    }
  }

  /** @param {string} s */
  function normalizeOrigin(s) {
    let t = String(s || '')
      .trim()
      .replace(/\/$/, '')
    if (!t) return ''
    if (!/^https?:\/\//i.test(t)) {
      if (/^[\d.]+(:\d+)?$/i.test(t) || /^(localhost|127\.0\.0\.1)(:\d+)?$/i.test(t)) {
        t = 'http://' + t
      } else {
        t = 'https://' + t
      }
    }
    try {
      return new URL(t).origin
    } catch {
      return ''
    }
  }

  function healthUrl(baseOrigin) {
    return new URL('/api/health', baseOrigin).toString()
  }

  function apiRoot(baseOrigin) {
    return new URL('/api', baseOrigin).toString().replace(/\/$/, '')
  }

  function sanitizeFilename(name) {
    let n = String(name || '').trim()
    if (!n) return 'email'
    n = n.replace(/[^A-Za-z0-9._@-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '')
    return n || 'email'
  }

  function matterLabel(c) {
    const num = c.case_number != null ? String(c.case_number) : ''
    const client = c.client_name ? String(c.client_name) : ''
    const title = c.matter_description != null ? String(c.matter_description) : ''
    const primary = [num, client].filter(Boolean).join(' — ') || String(c.id)
    return title ? primary + ' — ' + title : primary
  }

  function matterSearchText(c) {
    return matterLabel(c).toLowerCase()
  }

  function filterCases(query) {
    const q = String(query || '')
      .trim()
      .toLowerCase()
    if (!q) return []
    return allCases.filter((c) => matterSearchText(c).includes(q))
  }

  function setCaseSelection(caseId, labelText) {
    selectedCaseId = caseId ? String(caseId) : ''
    const selEl = $('case-selected')
    if (selEl) {
      if (selectedCaseId && labelText) {
        selEl.hidden = false
        selEl.textContent = 'Selected: ' + labelText
      } else {
        selEl.hidden = true
        selEl.textContent = ''
      }
    }
    const fileBtn = $('btn-file')
    if (fileBtn) fileBtn.disabled = !selectedCaseId
  }

  function renderCaseResults() {
    const box = $('case-results')
    const input = $('case-search')
    if (!box || !input) return

    if (input.disabled || !allCases.length) {
      box.innerHTML = ''
      box.hidden = true
      return
    }

    box.innerHTML = ''
    const q = String(input.value || '').trim()

    if (!q) {
      const hint = document.createElement('div')
      hint.className = 'case-results-empty muted'
      hint.textContent = 'Type in the box to search matters.'
      box.appendChild(hint)
      box.hidden = false
      return
    }

    const matches = filterCases(input.value)
    if (!matches.length) {
      const empty = document.createElement('div')
      empty.className = 'case-results-empty muted'
      empty.textContent = 'No matters match your search.'
      box.appendChild(empty)
      box.hidden = false
      return
    }

    const maxRows = 80
    const rows = matches.length > maxRows ? matches.slice(0, maxRows) : matches
    for (const c of rows) {
      const id = String(c.id)
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'case-result-row' + (id === selectedCaseId ? ' is-selected' : '')
      btn.setAttribute('role', 'option')
      btn.dataset.caseId = id
      btn.textContent = matterLabel(c)
      btn.onclick = () => {
        setCaseSelection(id, matterLabel(c))
        void renderCaseResults()
      }
      box.appendChild(btn)
    }

    if (matches.length > maxRows) {
      const more = document.createElement('div')
      more.className = 'case-results-more muted'
      more.textContent =
        'Showing ' + maxRows + ' of ' + matches.length + ' matches. Type more to narrow the list.'
      box.appendChild(more)
    }

    box.hidden = false
  }

  function setAuthPanels(signedIn) {
    const pre = $('panel-pre-auth')
    const post = $('panel-post-auth')
    if (pre) pre.classList.toggle('panel-hidden', !!signedIn)
    if (post) post.classList.toggle('panel-hidden', !signedIn)
    if (signedIn) {
      const ext0 = getExt()
      if (ext0) void syncMailDescriptionField(ext0)
    }
  }

  function mailItemSubjectFromHeader(header) {
    try {
      return String((header && header.subject) || 'email').trim() || 'email'
    } catch {
      return 'email'
    }
  }

  async function syncMailDescriptionField(ext) {
    const el = $('mail-description')
    if (!el) return
    if (el.dataset.userEdited === '1') return
    try {
      const got = await getSingleMessageHeaderOrError(ext)
      if (got.header) {
        el.value = mailItemSubjectFromHeader(got.header)
      }
    } catch (_) {
      el.value = ''
    }
  }

  function loginShowErr(msg) {
    const el = $('login-err')
    if (!el) return
    el.hidden = !msg
    el.textContent = msg || ''
  }

  async function getJwt(ext) {
    const o = await ext.storage.local.get(JWT_KEY)
    return (o && o[JWT_KEY]) || ''
  }

  async function setJwt(ext, token) {
    if (token) await ext.storage.local.set({ [JWT_KEY]: token })
    else await ext.storage.local.remove(JWT_KEY)
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

  async function apiGetCases(token, origin) {
    const res = await fetch(apiRoot(origin) + '/cases', { headers: authHeaders(token) })
    const ct = (res.headers.get('content-type') || '').toLowerCase()
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      if (res.status === 401) {
        const detail = body && typeof body === 'object' && body.detail
        throw new Error(typeof detail === 'string' ? detail : '401 Unauthorized')
      }
      const detail = body && typeof body === 'object' && body.detail
      const msg = typeof detail === 'string' ? detail : 'Could not load matters.'
      throw new Error(msg)
    }
    if (!Array.isArray(body)) {
      if (ct.includes('text/html')) {
        throw new Error('Matters request returned HTML (wrong API URL or session).')
      }
      throw new Error('Matters request returned an unexpected JSON shape.')
    }
    return body
  }

  async function apiGetMe(token, origin) {
    const res = await fetch(apiRoot(origin) + '/auth/me', { headers: authHeaders(token) })
    const ct = (res.headers.get('content-type') || '').toLowerCase()
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      if (res.status === 401) {
        const detail = body && typeof body === 'object' && body.detail
        throw new Error(typeof detail === 'string' ? detail : '401 Unauthorized')
      }
      const detail = body && typeof body === 'object' && body.detail
      const msg = typeof detail === 'string' ? detail : 'Could not verify session.'
      throw new Error(msg)
    }
    if (!body || typeof body !== 'object' || !body.email) {
      if (ct.includes('text/html')) {
        throw new Error('Session check returned HTML (wrong API URL).')
      }
      throw new Error('Session check returned an unexpected response.')
    }
    return body
  }

  async function resolveImapRefs(ext, header) {
    let mbox = ''
    const uid = header && header.id != null ? String(header.id) : ''
    const fref = header && header.folder
    if (fref && typeof fref === 'object' && !Array.isArray(fref)) {
      if (fref.path) mbox = String(fref.path).trim()
      else if (fref.name) mbox = String(fref.name).trim()
    }
    let folderId = null
    if (header && header.folder != null) {
      const f = header.folder
      if (typeof f === 'string' || typeof f === 'number') folderId = f
      else if (typeof f === 'object' && f.id != null) folderId = f.id
    }
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

  async function apiGetLinkedCase(token, origin, internetMessageId, imapRefs) {
    const res = await fetch(apiRoot(origin) + '/mail-plugin/linked-case', {
      method: 'POST',
      headers: jsonAuthHeaders(token),
      body: JSON.stringify({
        outlook_item_id: null,
        internet_message_id: internetMessageId || null,
        source_imap_mbox: (imapRefs && imapRefs.mbox) || null,
        source_imap_uid: (imapRefs && imapRefs.uid) || null,
      }),
    })
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      const detail = body && typeof body === 'object' && body.detail
      const msg = typeof detail === 'string' ? detail : 'Could not look up matter.'
      throw new Error(msg)
    }
    return body
  }

  function rawToBlob(raw) {
    if (typeof File !== 'undefined' && raw instanceof File) {
      return raw
    }
    if (raw instanceof ArrayBuffer) {
      return new Blob([raw], { type: 'message/rfc822' })
    }
    if (typeof raw === 'string') {
      const buf = new Uint8Array(raw.length)
      for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i) & 0xff
      return new Blob([buf], { type: 'message/rfc822' })
    }
    throw new Error('Unexpected raw message format from Thunderbird.')
  }

  /**
   * With no tabId, messageDisplay / mailTabs use the **globally** active tab. A companion window is a
   * `popup` whose active tab is the extension page, so APIs throw (e.g. "Invalid mail tab ID: 6").
   * Resolve a real `MailTab.id` from the 3‑pane or a standalone read window.
   * @param {object} ext
   * @returns {Promise<number|undefined>}
   */
  async function resolveMessageMailTabId(ext) {
    if (!ext.mailTabs) {
      return undefined
    }
    if (typeof ext.mailTabs.getCurrent === 'function') {
      try {
        const cur = await ext.mailTabs.getCurrent()
        if (cur && cur.id != null) {
          return cur.id
        }
      } catch (e) {
        /* e.g. no mail tab in front */
      }
    }
    var rows
    try {
      rows = (await ext.mailTabs.query({ active: true })) || []
    } catch (e) {
      return undefined
    }
    if (!Array.isArray(rows) || !rows.length) {
      return undefined
    }
    if (rows.length === 1) {
      return rows[0].id
    }
    if (!ext.windows || typeof ext.windows.get !== 'function') {
      return rows[0].id
    }
    const rank = function (t) {
      if (t === 'normal') {
        return 0
      }
      if (t === 'messageDisplay') {
        return 1
      }
      if (t === 'popup' || t === 'messageCompose') {
        return 9
      }
      return 5
    }
    const scored = []
    for (const mt of rows) {
      if (!mt || mt.id == null) {
        continue
      }
      var r = 5
      try {
        const w = await ext.windows.get(mt.windowId)
        if (w && w.type) {
          r = rank(String(w.type))
        }
      } catch (e) {
        r = 5
      }
      scored.push({ id: mt.id, r: r })
    }
    scored.sort(function (a, b) {
      return a.r - b.r
    })
    if (scored.length) {
      return scored[0].id
    }
    return rows[0].id
  }

  async function resolveContextFilingMessageId(ext) {
    let mid = null
    if (contextFilingMessageId && contextFilingMessageId !== true) {
      mid = normalizeMessageId(contextFilingMessageId)
    }
    if (mid == null) {
      const key =
        globalThis.canaryContextFilingMessageKey || 'canary_context_filing_message_id'
      try {
        const sess = await ext.storage.session.get(key)
        mid = normalizeMessageId(sess && sess[key])
      } catch (_) {
        /* session optional */
      }
    }
    return mid
  }

  /** @returns {Promise<{ header?: object, error?: string }>} */
  async function getSingleMessageHeaderOrError(ext) {
    if (contextFilingMessageId) {
      const ctxHeader = await getContextFilingHeader(ext)
      if (ctxHeader) return { header: ctxHeader }
    }
    const tabId = await resolveMessageMailTabId(ext)
    if (tabId == null && isCompanion) {
      return {
        error:
          'No mail view found. Focus the main mail window (or a message window), then return here. The companion window is not a mail view.',
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
      } catch {
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
      } catch (e) {
        messages = []
      }
    }
    if (!messages.length) {
      return { error: 'No message in view. Open or select a single message.' }
    }
    if (messages.length > 1) {
      return { error: 'Select only one message to see its filing state or to file it.' }
    }
    return { header: messages[0] }
  }

  async function getSingleMessageHeader(ext) {
    const o = await getSingleMessageHeaderOrError(ext)
    if (o.error) throw new Error(o.error)
    if (!o.header) throw new Error('No message.')
    return o.header
  }

  /** Message header from right-click → File to Canary matter (URL or session storage). */
  async function getContextFilingHeader(ext) {
    const mid = await resolveContextFilingMessageId(ext)
    if (mid == null) return null
    if (ext.messages && typeof ext.messages.get === 'function') {
      try {
        const full = await ext.messages.get(mid)
        if (full) return full
      } catch (_) {
        /* fall through */
      }
    }
    if (ext.messages && typeof ext.messages.getFull === 'function') {
      try {
        const full = await ext.messages.getFull(mid)
        if (full && full.id != null) return full
      } catch (_) {
        /* fall through */
      }
    }
    return { id: mid, subject: '' }
  }

  function resetFilingFormForNewMessage() {
    linkedCaseId = ''
    setCaseSelection('', '')
    const searchInput = $('case-search')
    if (searchInput) searchInput.value = ''
    const mailDesc = $('mail-description')
    if (mailDesc) {
      mailDesc.value = ''
      delete mailDesc.dataset.userEdited
    }
    const caseSel = $('case-selected')
    if (caseSel) {
      caseSel.hidden = true
      caseSel.textContent = ''
    }
    const results = $('case-results')
    if (results) {
      results.hidden = true
      results.innerHTML = ''
    }
    const outEl = $('out')
    if (outEl) {
      outEl.className = ''
      outEl.textContent = ''
    }
    renderCaseResults()
  }

  function refreshContextFilingMessageIdFromUrl() {
    try {
      const params = new URLSearchParams(String(globalThis.location.search || ''))
      if (params.get('contextFiling') !== '1') return
      const mid = normalizeMessageId(params.get('messageId'))
      if (mid != null) contextFilingMessageId = mid
    } catch (_) {
      /* ignore */
    }
  }

  /**
   * Context filing reuses one pop-out window — refresh UI for the current message id.
   * @param {typeof messenger} ext
   */
  async function bootstrapContextFiling(ext) {
    refreshContextFilingMessageIdFromUrl()
    if (!contextFilingMessageId) return
    const mid = await resolveContextFilingMessageId(ext)
    const el = $('linked-case-line')
    if (mid == null) {
      if (el) {
        setLinkedCaseLineEl(el, {
          text: 'Could not read the selected message. Right-click the message and try again.',
          state: 'warn',
        })
      }
      return
    }
    contextFilingMessageId = mid
    contextFilingLoadedForMessageId = mid
    resetFilingFormForNewMessage()
    const token = await getJwt(ext)
    let origin = ''
    try {
      origin = await requireOrigin(ext)
    } catch (e) {
      if (el) {
        setLinkedCaseLineEl(el, {
          text: e && e.message ? String(e.message) : 'Set your Canary site and sign in.',
          state: 'warn',
        })
      }
      return
    }
    if (!token || !origin) {
      if (el) {
        setLinkedCaseLineEl(el, {
          text: 'Sign in via Server & sign-in to file this message.',
          state: 'warn',
        })
      }
      return
    }
    await refreshLinkedCaseBanner(ext, token, origin)
    await syncMailDescriptionField(ext)
  }

  /**
   * @param {typeof messenger} ext
   * @param {string} token
   * @param {string} origin
   */
  async function refreshLinkedCaseBanner(ext, token, origin) {
    const el = $('linked-case-line')
    if (!el) return
    if (!token || !origin) {
      setLinkedCaseLineEl(el, { text: '—', state: 'muted' })
      return
    }
    setLinkedCaseLineEl(el, { text: 'Loading matter…', state: 'muted' })
    const got = await getSingleMessageHeaderOrError(ext)
    if (got.error) {
      linkedCaseId = ''
      setCaseSelection('', '')
      renderCaseResults()
      setLinkedCaseLineEl(el, { text: got.error, state: 'warn' })
      return
    }
    let h = got.header
    if (h && h.id != null && ext.messages) {
      const mid0 = h.headerMessageId ? String(h.headerMessageId).trim() : ''
      if (!mid0 && typeof ext.messages.getFull === 'function') {
        try {
          const full = await ext.messages.getFull(h.id, { decodeHeaders: true })
          const hdrs = full && full.headers
          if (hdrs && typeof hdrs === 'object') {
            const keys = Object.keys(hdrs)
            for (let i = 0; i < keys.length; i++) {
              if (String(keys[i]).toLowerCase() === 'message-id') {
                const v = hdrs[keys[i]]
                const parsed = Array.isArray(v) ? String(v[0] || '').trim() : String(v || '').trim()
                if (parsed) {
                  h = Object.assign({}, h, { headerMessageId: parsed })
                }
                break
              }
            }
          }
        } catch (_) {
          /* optional */
        }
      }
    }
    const mid = (h && h.headerMessageId) ? String(h.headerMessageId).trim() : ''
    /** When Message-ID is present, match on that only — avoid false positives from IMAP OR in the API. */
    const imapRefs = mid ? { mbox: '', uid: '' } : await resolveImapRefs(ext, h)
    if (!mid && !(imapRefs.mbox && imapRefs.uid)) {
      linkedCaseId = ''
      setCaseSelection('', '')
      renderCaseResults()
      setLinkedCaseLineEl(el, {
        text: 'This message has no Message-ID header and no IMAP reference, so Canary cannot match it to a prior filing.',
        state: 'warn',
      })
      return
    }
    try {
      const body = await apiGetLinkedCase(token, origin, mid, imapRefs)
      const lc = body && body.linked_case
      if (lc && lc.id) {
        linkedCaseId = String(lc.id)
        setCaseSelection(linkedCaseId, matterLabel(lc))
        setLinkedCaseLineEl(el, {
          text: 'Filed in Canary: ' + matterLabel(lc),
          state: 'ok',
        })
      } else {
        linkedCaseId = ''
        setCaseSelection('', '')
        setLinkedCaseLineEl(el, {
          text: 'Not found in Canary yet (or no access) — you can file it to a matter below.',
          state: 'muted',
        })
      }
      void renderCaseResults()
    } catch (e) {
      linkedCaseId = ''
      setCaseSelection('', '')
      renderCaseResults()
      setLinkedCaseLineEl(el, {
        text: e && e.message ? String(e.message) : 'Could not look up matter.',
        state: 'warn',
      })
    }
  }

  /**
   * Apply “Canary” tag via messages.update in this window when possible (cached key from background).
   * Falls back to runtime.sendMessage for tag list/create in the background script.
   */
  async function applyCanaryFiledTagLocal(ext, messageId) {
    const id0 = normalizeMessageId(messageId)
    if (id0 == null || !ext.messages || typeof ext.messages.update !== 'function') {
      return { ok: false, detail: 'messages.update is not available in this window.' }
    }
    const st = await ext.storage.local.get(['canary_tag_key'])
    const key = st && st.canary_tag_key ? String(st.canary_tag_key) : ''
    if (key) {
      try {
        let list = []
        try {
          const msg = await ext.messages.get(id0)
          list = msg && Array.isArray(msg.tags) ? msg.tags.slice() : []
        } catch (_) {
          list = []
        }
        if (list.indexOf(key) === -1) {
          list = list.slice()
          list.push(key)
        }
        await ext.messages.update(id0, { tags: list })
        return { ok: true, detail: 'The “Canary” message tag was applied in the list.' }
      } catch (e1) {
        try {
          await ext.messages.update(id0, { tags: [key] })
          return { ok: true, detail: 'The “Canary” message tag was applied in the list.' }
        } catch (e2) {
          try {
            await ext.messages.update(id0, { flagged: true })
            return {
              ok: true,
              detail:
                'Tag apply failed; starred the message instead. (' +
                ((e2 && e2.message) || String(e2)) +
                ')',
            }
          } catch (e3) {
            return { ok: false, detail: (e2 && e2.message) || String(e2) }
          }
        }
      }
    }
    try {
      await ext.messages.update(id0, { flagged: true })
      return {
        ok: true,
        detail: 'Starred the message (Canary tag key not ready — reload the add-on once).',
      }
    } catch (e) {
      return { ok: false, detail: (e && e.message) || String(e) }
    }
  }

  async function applyCanaryFiledTagFromBackground(ext, messageId) {
    const local = await applyCanaryFiledTagLocal(ext, messageId)
    if (local.ok) return local
    if (!ext || !ext.runtime || !ext.runtime.sendMessage) {
      return local.ok === false ? local : { ok: false, detail: 'Extension runtime not available' }
    }
    return new Promise(function (resolve) {
      ext.runtime.sendMessage(
        { type: 'canary-apply-filed-tag', messageId: messageId },
        function (r) {
          if (ext.runtime.lastError) {
            const err = String(ext.runtime.lastError.message)
            if (/receiving end does not exist/i.test(err)) {
              resolve(local.ok === false ? local : { ok: false, detail: err })
              return
            }
            resolve({ ok: false, detail: err })
            return
          }
          if (r && typeof r === 'object' && 'ok' in r) {
            resolve(r)
          } else {
            resolve(local.ok === false ? local : { ok: false, detail: 'No or invalid response from background' })
          }
        },
      )
    })
  }

  function readOriginFromInput() {
    return normalizeOrigin($('apiOrigin') && $('apiOrigin').value)
  }

  async function requireOrigin(ext) {
    const fromInput = readOriginFromInput()
    if (fromInput) return fromInput
    const obj = await ext.storage.local.get(ORIGIN_KEY)
    return normalizeOrigin((obj && obj[ORIGIN_KEY]) || '')
  }

  async function isSessionReady(ext) {
    const t = await getJwt(ext)
    if (!t) return false
    const o = await requireOrigin(ext)
    return !!o
  }

  function wirePopoutCloseButton() {
    const btn = $('btn-close-popout')
    if (!btn) return
    const isPopout = !!(contextFilingMessageId || isCompanion)
    if (!isPopout) {
      btn.hidden = true
      return
    }
    btn.hidden = false
    btn.addEventListener('click', function () {
      globalThis.close()
    })
  }

  function main() {
    const originInput = $('apiOrigin')
    const outEl = $('out')
    const testBtn = $('test')
    const ext = getExt()
    wirePopoutCloseButton()
    const blockSetup = $('block-setup')
    const blockFiling = $('block-filing')
    const backFilingWrap = $('setup-filing-back-wrap')
    const mailDesc = $('mail-description')

    async function syncBlockVisibility() {
      const ready = await isSessionReady(ext)
      const showServer = !ready || settingsOpen
      if (blockSetup) blockSetup.hidden = !showServer
      if (blockFiling) blockFiling.hidden = showServer
      if (backFilingWrap) backFilingWrap.hidden = !(ready && settingsOpen)
      setSubhead(showServer ? 'server' : 'filing')
      if (!showServer) {
        const t = await getJwt(ext)
        const o = await requireOrigin(ext)
        if (t && o) {
          if (contextFilingMessageId) {
            void bootstrapContextFiling(ext)
          } else {
            void refreshLinkedCaseBanner(ext, t, o)
          }
        }
      }
    }

    if (!ext || !ext.storage || !ext.storage.local) {
      out(
        outEl,
        'This window does not have the Thunderbird add-on API (messenger.storage). ' +
          'Open it from the Canary toolbar button on the main Thunderbird window, not a browser tab.',
        true,
      )
      if (testBtn) testBtn.disabled = true
      return
    }

    void syncBlockVisibility()

    if (contextFilingMessageId) {
      globalThis.addEventListener('pageshow', function () {
        void bootstrapContextFiling(ext)
      })
    }

    ext.storage.local
      .get(ORIGIN_KEY)
      .then((obj) => {
        const o = (obj && obj[ORIGIN_KEY]) || ''
        if (originInput && o) originInput.value = o
      })
      .catch((e) => {
        out(outEl, 'Could not read settings: ' + (e && e.message ? e.message : String(e)), true)
      })

    const searchInput = $('case-search')
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        if (selectedCaseId) {
          const visible = filterCases(searchInput.value)
          const still = visible.some((c) => String(c.id) === selectedCaseId)
          const linked = linkedCaseId && String(linkedCaseId) === String(selectedCaseId)
          if (!still && !linked) setCaseSelection('', '')
        }
        renderCaseResults()
      })
    }

    if (mailDesc) {
      mailDesc.addEventListener('input', () => {
        mailDesc.dataset.userEdited = '1'
      })
    }

    async function testConnection() {
      if (!originInput) return
      out(outEl, 'Checking — saving URL, then calling /api/health…', 'busy')
      const n = normalizeOrigin(originInput.value)
      if (!n) {
        out(
          outEl,
          'Need a full URL, e.g. http://127.0.0.1:8080 (port 8080 is the default nginx UI in our Docker compose).',
          true,
        )
        return
      }
      originInput.value = n
      let clearedJwt = false
      try {
        const prevSt = await ext.storage.local.get(ORIGIN_KEY)
        const prevOrigin = normalizeOrigin((prevSt && prevSt[ORIGIN_KEY]) || '')
        if (prevOrigin && prevOrigin !== n) {
          await setJwt(ext, '')
          clearedJwt = true
        }
        await ext.storage.local.set({ [ORIGIN_KEY]: n })
      } catch (e) {
        out(outEl, 'Could not save: ' + (e && e.message ? e.message : String(e)), true)
        return
      }

      const url = healthUrl(n)
      try {
        const res = await fetch(url, { method: 'GET', cache: 'no-store' })
        const text = await res.text()
        let showBody = text
        try {
          const j = JSON.parse(text)
          showBody = JSON.stringify(j, null, 0)
        } catch {
          /* not JSON */
        }
        if (res.ok) {
          const signInHint = clearedJwt
            ? '\n\nSite URL changed — sign in again below.'
            : ''
          out(
            outEl,
            'Connected. API answered at /api/health.\n' + 'URL: ' + url + '\n' + 'Response: ' + showBody + signInHint,
            false,
          )
        } else {
          out(
            outEl,
            'The server answered but with an error.\n' + 'URL: ' + url + '\n' + 'HTTP ' + res.status + '\n' + showBody,
            true,
          )
        }
        await refreshAuthAndCases(ext, n, { preferFilingOnSuccess: true })
      } catch (e) {
        const err = e && e.message ? e.message : String(e)
        out(
          outEl,
          'FAILED to reach your Canary site.\n' + err + '\n\n' + 'Tried: ' + url,
          true,
        )
      }
    }

    async function refreshAuthAndCases(ext, origin, opts) {
      const token = await getJwt(ext)
      const authEl = $('auth-status')
      const fileBtn = $('btn-file')
      if (authEl) authEl.textContent = token ? 'Loading…' : ''
      if (fileBtn) fileBtn.disabled = true
      if (searchInput) {
        searchInput.value = ''
        searchInput.disabled = true
      }
      allCases = []
      setCaseSelection('', '')
      const results = $('case-results')
      if (results) {
        results.innerHTML = ''
        results.hidden = true
      }

      if (!token) {
        setAuthPanels(false)
        loginShowErr('')
        if (searchInput) {
          searchInput.disabled = true
          searchInput.placeholder = 'Sign in to search matters'
        }
        void syncBlockVisibility()
        return
      }

      setAuthPanels(true)
      if (searchInput) {
        searchInput.disabled = true
        searchInput.placeholder = 'Loading…'
      }
      try {
        const cases = await apiGetCases(token, origin)
        allCases = Array.isArray(cases) ? cases : []
        let meEmail = ''
        try {
          const me = await apiGetMe(token, origin)
          if (me && me.email) meEmail = String(me.email)
        } catch {
          /* */
        }
        const who = meEmail ? 'Signed in as ' + meEmail : 'Signed in'
        if (authEl) authEl.textContent = who + ' · ' + allCases.length + ' matter(s).'
        if (searchInput) {
          searchInput.disabled = false
          searchInput.placeholder = allCases.length ? 'Type to search…' : 'No matters — create in Canary'
        }
        if (opts && opts.preferFilingOnSuccess) settingsOpen = false
        if (searchInput) searchInput.value = ''
        linkedCaseId = ''
        setCaseSelection('', '')
        void syncBlockVisibility()
        renderCaseResults()
      } catch (e) {
        const msg = e && e.message ? String(e.message) : 'Failed to load matters.'
        out($('out'), msg, true)
        if (msg === '401 Unauthorized' || (globalThis.canaryShared && globalThis.canaryShared.isAuthSessionErrorMessage(msg))) {
          await setJwt(ext, '')
          if (authEl) authEl.textContent = ''
          setAuthPanels(false)
          settingsOpen = true
          loginShowErr('Session expired or the Canary site changed — sign in again.')
        }
        allCases = []
        if (searchInput) {
          searchInput.disabled = msg !== '401 Unauthorized'
          searchInput.placeholder = msg === '401 Unauthorized' ? 'Sign in to search matters' : 'Type to search…'
        }
        if (results) {
          results.innerHTML = ''
          results.hidden = true
        }
        void syncBlockVisibility()
      }
    }

    async function submitLogin() {
      loginShowErr('')
      out($('out'), '', false)
      const origin = await requireOrigin(ext)
      if (!origin) {
        out($('out'), 'Enter your Canary site URL, then use Test connection.', true)
        return
      }
      if (originInput && !originInput.value) originInput.value = origin
      const email = ($('login-email') && $('login-email').value.trim()) || ''
      const password = ($('login-password') && $('login-password').value) || ''
      const totp = ($('login-totp') && $('login-totp').value.trim()) || ''
      if (!email || !password) {
        loginShowErr('Email and password are required.')
        return
      }
      try {
        const res = await fetch(apiRoot(origin) + '/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, totp_code: totp || null }),
        })
        const body = await res.json().catch(() => null)
        if (!res.ok) {
          const detail = body && typeof body === 'object' && body.detail
          const msg =
            typeof detail === 'string'
              ? detail
              : res.status === 401
                ? 'Invalid credentials or 2FA required.'
                : 'Sign-in failed.'
          loginShowErr(msg)
          return
        }
        const at = body && body.access_token
        if (!at) {
          loginShowErr('No access token returned.')
          return
        }
        await setJwt(ext, at)
        if ($('login-password')) $('login-password').value = ''
        if ($('login-totp')) $('login-totp').value = ''
        settingsOpen = false
        await refreshAuthAndCases(ext, origin, { preferFilingOnSuccess: true })
      } catch (e) {
        loginShowErr(e && e.message ? String(e.message) : 'Network error.')
      }
    }

    async function uploadEml(token, origin, caseId, blob, filename, imapRefs, internetMessageId) {
      const fd = new FormData()
      fd.append('upload', blob, filename)
      fd.append('folder', '')
      if (imapRefs && imapRefs.mbox) fd.append('source_imap_mbox', imapRefs.mbox)
      if (imapRefs && imapRefs.uid) fd.append('source_imap_uid', imapRefs.uid)
      if (internetMessageId) fd.append('source_internet_message_id', internetMessageId)

      const res = await fetch(apiRoot(origin) + '/cases/' + encodeURIComponent(caseId) + '/files', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + token },
        body: fd,
      })
      const body = await res.json().catch(() => null)
      if (!res.ok) {
        const detail = body && typeof body === 'object' && body.detail
        const msg = typeof detail === 'string' ? detail : 'Upload failed (' + res.status + ')'
        throw new Error(msg)
      }
      if (!body || typeof body !== 'object' || !body.id) {
        throw new Error('Upload succeeded but no file id returned.')
      }
      return body
    }

    /**
     * @returns {Promise<object>} MessageHeader
     */
    async function fileMessageToCaseInternal(ext, token, origin, caseId) {
      if (!ext.messages || typeof ext.messages.getRaw !== 'function') {
        throw new Error('messages.getRaw is not available in this build.')
      }
      let header = null
      if (contextFilingMessageId) {
        header = await getContextFilingHeader(ext)
      }
      if (!header) {
        header = await getSingleMessageHeader(ext)
      }
      if (header.headersOnly) {
        throw new Error('Message body not downloaded; wait for the message to load fully, then try again.')
      }
      const rawId = normalizeMessageId(header.id)
      if (rawId == null) {
        throw new Error('Invalid message id for filing.')
      }
      const raw = await ext.messages.getRaw(rawId)
      const blob = rawToBlob(raw)
      const descRaw = mailDesc ? String(mailDesc.value || '').trim() : ''
      const displayBase = descRaw || mailItemSubjectFromHeader(header)
      const parentName = sanitizeFilename(displayBase) + '.eml'
      const imapRefs = await resolveImapRefs(ext, header)
      let internetMid = header.headerMessageId ? String(header.headerMessageId).trim() : ''
      if (!internetMid && ext.messages && typeof ext.messages.getFull === 'function') {
        try {
          const full = await ext.messages.getFull(rawId, { decodeHeaders: true })
          const hdrs = full && full.headers
          if (hdrs && typeof hdrs === 'object') {
            const keys = Object.keys(hdrs)
            for (let i = 0; i < keys.length; i++) {
              if (String(keys[i]).toLowerCase() === 'message-id') {
                const v = hdrs[keys[i]]
                internetMid = Array.isArray(v) ? String(v[0] || '').trim() : String(v || '').trim()
                break
              }
            }
          }
        } catch (_) {
          /* optional */
        }
      }
      const uploaded = await uploadEml(token, origin, caseId, blob, parentName, imapRefs, internetMid || null)
      return { header: header, fileId: uploaded && uploaded.id != null ? String(uploaded.id) : null }
    }

    if (testBtn) testBtn.addEventListener('click', () => void testConnection())
    if (originInput) {
      originInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          void testConnection()
        }
      })
    }

    const signIn = $('btn-sign-in')
    if (signIn) signIn.onclick = () => void submitLogin()
    if ($('login-email') && signIn) {
      $('login-email').addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault()
          signIn.click()
        }
      })
    }
    if ($('login-password') && signIn) {
      $('login-password').addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault()
          signIn.click()
        }
      })
    }

    const btnLogout = $('btn-logout')
    if (btnLogout) {
      btnLogout.onclick = () => {
        void (async () => {
          try {
            await setJwt(ext, '')
            if (mailDesc) {
              mailDesc.value = ''
              delete mailDesc.dataset.userEdited
            }
            await refreshAuthAndCases(ext, (await requireOrigin(ext)) || '', {})
            out($('out'), 'Signed out.', false)
            await syncBlockVisibility()
          } catch (e) {
            out($('out'), e && e.message ? String(e.message) : 'Could not sign out.', true)
          }
        })()
      }
    }

    const btnOpenSetup = $('btn-open-setup')
    if (btnOpenSetup) {
      btnOpenSetup.onclick = () => {
        settingsOpen = true
        void syncBlockVisibility()
      }
    }
    const btnFilingBack = $('btn-filing-back')
    if (btnFilingBack) {
      btnFilingBack.onclick = () => {
        settingsOpen = false
        out($('out'), '', false)
        void syncBlockVisibility()
      }
    }

    if (isCompanion) {
      const cl = $('companion-launch-wrap')
      if (cl) cl.hidden = true
    } else {
      const openCompanion = $('btn-open-companion')
      if (openCompanion) {
        openCompanion.addEventListener('click', () => {
          void (async () => {
            if (!ext.runtime || !ext.runtime.sendMessage) {
              out($('out'), 'Runtime messaging not available.', true)
              return
            }
            const r = await new Promise((resolve) => {
              ext.runtime.sendMessage(
                { type: 'canary-open-companion' },
                (resp) => {
                  if (ext.runtime.lastError) {
                    resolve({ ok: false, detail: String(ext.runtime.lastError.message) })
                    return
                  }
                  resolve(resp)
                },
              )
            })
            if (!r || !r.ok) {
              out($('out'), (r && r.detail) || 'Could not open the window.', true)
              return
            }
            if (r && r.focused) {
              out($('out'), 'Brought the existing Canary window to the front.', false)
            } else {
              out($('out'), 'Opened the Canary window. Resize it and keep it open while you work in the main window.', false)
            }
          })()
        })
      }
    }

    const fileBtn = $('btn-file')
    if (fileBtn) {
      fileBtn.onclick = () => {
        void (async () => {
          const origin = await requireOrigin(ext)
          if (!origin) {
            out($('out'), 'Connection lost — use Server & sign-in to set your site.', true)
            return
          }
          const token = await getJwt(ext)
          const caseId = selectedCaseId
          if (!token || !caseId) return
          out($('out'), 'Uploading message…', 'busy')
          fileBtn.disabled = true
          try {
            const filed = await fileMessageToCaseInternal(ext, token, origin, caseId)
            const header = filed && filed.header ? filed.header : filed
            const fileId = filed && filed.fileId != null ? filed.fileId : null
            if (ext.runtime && ext.runtime.sendMessage && header && header.id != null) {
              await new Promise(function (resolve) {
                ext.runtime.sendMessage(
                  {
                    type: 'canary-record-filed-message',
                    tbMessageId: header.id,
                    caseId: caseId,
                    fileId: fileId,
                    internetMessageId: header.headerMessageId || null,
                  },
                  function () {
                    resolve()
                  },
                )
              })
            }
            if (mailDesc) {
              mailDesc.value = ''
              delete mailDesc.dataset.userEdited
            }
            await syncMailDescriptionField(ext)
            const tagResult = await applyCanaryFiledTagFromBackground(
              ext,
              normalizeMessageId(header.id),
            )
            let msg = 'Saved to Canary. The “Canary” message tag should appear in the thread list (turn on the Tags column if you use it).'
            if (tagResult && tagResult.ok && tagResult.detail) {
              msg = 'Saved to Canary. ' + tagResult.detail
            } else if (tagResult && !tagResult.ok && tagResult.detail) {
              msg = 'Saved to Canary. (Marking: ' + tagResult.detail + ')'
            }
            out($('out'), msg, false)
            await refreshLinkedCaseBanner(ext, token, origin)
          } catch (e) {
            out($('out'), e && e.message ? String(e.message) : 'Failed.', true)
          } finally {
            fileBtn.disabled = !selectedCaseId
          }
        })()
      }
    }

    void (async () => {
      if (contextFilingMessageId) {
        const sub = $('subhead')
        if (sub) {
          sub.textContent = 'File the message you right-clicked to a matter.'
        }
      }
      const t = await getJwt(ext)
      const o = await requireOrigin(ext)
      if (t && o) {
        settingsOpen = false
        await refreshAuthAndCases(ext, o, {})
        if (contextFilingMessageId) {
          contextFilingLoadedForMessageId = null
          await bootstrapContextFiling(ext)
        }
      } else {
        settingsOpen = false
        if (t && !o) {
          setAuthPanels(true)
          const a = $('auth-status')
          if (a) a.textContent = 'Set your Canary site URL above, then use Test connection.'
        } else {
          await refreshAuthAndCases(ext, o || '', {})
        }
        void syncBlockVisibility()
      }
    })()
  }

  try {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', main)
    } else {
      main()
    }
  } catch (e) {
    const o = document.getElementById('out')
    if (o) {
      o.classList.add('err')
      o.textContent = (e && e.message) || String(e)
    }
  }
})()
