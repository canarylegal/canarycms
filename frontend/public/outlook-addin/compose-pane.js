/* global Office */
;(function () {
  'use strict'

  const sh = function () {
    return globalThis.canaryOutlookShared
  }
  const applyApi = function () {
    return globalThis.canaryOutlookApplyCompose
  }
  const MAX_ATTACH = 25
  const ADDIN_UI_VERSION = '1.0.8.1'
  const DRAFT_KEY = 'canary_outlook_compose_draft'
  const ATTACH_STORAGE_PREFIX = 'canary_outlook_attach_'

  let allCases = []
  let selectedCase = null
  let caseFiles = []
  let caseContacts = []
  let precedents = []
  let selectedAttachIds = []
  let isReplyCompose = false
  /** @type {{ kind: 'none'|'all_clients'|'matter', matterId?: string, label?: string }} */
  let recipientPick = { kind: 'none' }

  function $(id) {
    return document.getElementById(id)
  }

  function showStatus(elId, text, asError) {
    const el = $(elId)
    if (!el) return
    el.style.display = text ? 'block' : 'none'
    el.textContent = text || ''
    el.className = asError ? 'error' : 'ok'
  }

  function loginShowErr(msg) {
    const el = $('login-err')
    if (!el) return
    el.style.display = msg ? 'block' : 'none'
    el.textContent = msg || ''
  }

  function setAuthPanels(signedIn) {
    const pre = $('panel-pre-auth')
    const post = $('panel-post-auth')
    if (pre) pre.classList.toggle('panel-hidden', !!signedIn)
    if (post) post.classList.toggle('panel-hidden', !signedIn)
  }

  async function apiGet(token, path) {
    const res = await fetch(sh().apiRoot() + path, { headers: sh().authHeaders(token) })
    const body = await res.json().catch(function () {
      return null
    })
    if (!res.ok) {
      if (res.status === 401) throw new Error('401 Unauthorized')
      const detail = body && body.detail
      throw new Error(typeof detail === 'string' ? detail : 'Request failed (' + res.status + ')')
    }
    return body
  }

  async function submitLogin() {
    loginShowErr('')
    showStatus('msg', '', true)
    showStatus('ok', '', false)
    const email = ($('login-email') && $('login-email').value.trim()) || ''
    const password = ($('login-password') && $('login-password').value) || ''
    const totp = ($('login-totp') && $('login-totp').value.trim()) || ''
    if (!email || !password) {
      loginShowErr('Email and password are required.')
      return
    }
    try {
      const res = await fetch(sh().apiRoot() + '/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, password: password, totp_code: totp || null }),
      })
      const body = await res.json().catch(function () {
        return null
      })
      if (!res.ok) {
        const detail = body && body.detail
        loginShowErr(typeof detail === 'string' ? detail : 'Sign-in failed.')
        return
      }
      const token = body && body.access_token
      if (!token) {
        loginShowErr('No access token returned.')
        return
      }
      await sh().persistTokenAsync(token)
      if ($('login-password')) $('login-password').value = ''
      if ($('login-totp')) $('login-totp').value = ''
      await refreshAuthAndCases()
    } catch (e) {
      loginShowErr(e && e.message ? String(e.message) : 'Network error.')
    }
  }

  function setCaseSelection(caseId, labelText) {
    const selEl = $('case-selected')
    if (selEl) {
      if (caseId && labelText) {
        selEl.hidden = false
        selEl.textContent = 'Selected: ' + labelText
      } else {
        selEl.hidden = true
        selEl.textContent = ''
      }
    }
  }

  function renderCaseResults() {
    const box = $('case-results')
    const input = $('case-search')
    if (!box || !input) return
    box.innerHTML = ''
    const q = String(input.value || '').trim()
    if (!q) {
      box.hidden = true
      return
    }
    const matches = sh().filterCases(allCases, q)
    if (!matches.length) {
      const empty = document.createElement('div')
      empty.className = 'case-results-empty muted'
      empty.textContent = 'No matters match your search.'
      box.appendChild(empty)
      box.hidden = false
      return
    }
    const rows = matches.length > 80 ? matches.slice(0, 80) : matches
    for (const c of rows) {
      const id = String(c.id)
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className =
        'case-result-row' + (selectedCase && String(selectedCase.id) === id ? ' is-selected' : '')
      btn.setAttribute('role', 'option')
      btn.textContent = sh().matterLabel(c)
      btn.onclick = function () {
        void selectCase(c)
      }
      box.appendChild(btn)
    }
    box.hidden = false
  }

  function contactLabel(cc) {
    const parts = [cc.name || 'Contact']
    if (cc.email) parts.push(cc.email)
    if (cc.matter_contact_reference) parts.push('Ref: ' + cc.matter_contact_reference)
    return parts.join(' — ')
  }

  function setRecipientPick(pick) {
    recipientPick = pick
    const el = $('recipient-selected')
    if (!el) return
    if (pick.kind === 'none') {
      el.textContent = 'Recipient: none (fill To yourself)'
    } else if (pick.kind === 'all_clients') {
      el.textContent = 'Recipient: all clients (merge fields only)'
    } else {
      el.textContent = 'Recipient: ' + (pick.label || pick.kind)
    }
    const box = $('recipient-pick')
    if (box) {
      box.querySelectorAll('[data-recipient]').forEach(function (btn) {
        btn.classList.remove('is-selected')
      })
      if (pick.kind === 'none' || pick.kind === 'all_clients') {
        const b = box.querySelector('[data-recipient="' + pick.kind + '"]')
        if (b) b.classList.add('is-selected')
      } else if (pick.kind === 'matter' && pick.matterId) {
        const b = box.querySelector('[data-recipient="matter:' + pick.matterId + '"]')
        if (b) b.classList.add('is-selected')
      }
    }
  }

  function renderRecipientPick() {
    const box = $('recipient-pick')
    if (!box) return
    box.innerHTML = ''
    const noneBtn = document.createElement('button')
    noneBtn.type = 'button'
    noneBtn.className = 'case-result-row'
    noneBtn.dataset.recipient = 'none'
    noneBtn.textContent = 'None'
    noneBtn.onclick = function () {
      setRecipientPick({ kind: 'none' })
    }
    box.appendChild(noneBtn)
    const allBtn = document.createElement('button')
    allBtn.type = 'button'
    allBtn.className = 'case-result-row'
    allBtn.dataset.recipient = 'all_clients'
    allBtn.textContent = 'All clients (merge only)'
    allBtn.onclick = function () {
      setRecipientPick({ kind: 'all_clients' })
    }
    box.appendChild(allBtn)
    for (const cc of caseContacts) {
      if (!cc.email) continue
      const id = String(cc.id)
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'case-result-row'
      btn.dataset.recipient = 'matter:' + id
      btn.textContent = contactLabel(cc)
      btn.onclick = function () {
        setRecipientPick({ kind: 'matter', matterId: id, label: contactLabel(cc) })
      }
      box.appendChild(btn)
    }
    setRecipientPick(recipientPick)
  }

  function fillFolderSelect() {
    const sel = $('folder')
    if (!sel) return
    const prev = sel.value
    sel.innerHTML = ''
    const o0 = document.createElement('option')
    o0.value = ''
    o0.textContent = 'None (matter root)'
    sel.appendChild(o0)
    for (const path of sh().collectFolderPaths(caseFiles)) {
      const o = document.createElement('option')
      o.value = path
      o.textContent = path
      sel.appendChild(o)
    }
    if (prev && Array.from(sel.options).some(function (o) {
      return o.value === prev
    })) {
      sel.value = prev
    }
  }

  function fillPrecedentSelect() {
    const sel = $('precedent')
    if (!sel) return
    const prev = sel.value
    sel.innerHTML = ''
    const o0 = document.createElement('option')
    o0.value = ''
    o0.textContent = '(none)'
    sel.appendChild(o0)
    for (const p of precedents) {
      const o = document.createElement('option')
      o.value = String(p.id)
      o.textContent = p.name || p.title || String(p.id)
      sel.appendChild(o)
    }
    if (prev && Array.from(sel.options).some(function (o) {
      return o.value === prev
    })) {
      sel.value = prev
    }
  }

  function updateAttachSummary() {
    const summary = $('attach-selected-summary')
    if (!summary) return
    const n = selectedAttachIds.length
    if (!n) {
      summary.textContent = 'No files selected for attach.'
      return
    }
    const names = []
    for (let i = 0; i < selectedAttachIds.length && names.length < 4; i++) {
      const id = selectedAttachIds[i]
      const f = caseFiles.find(function (x) {
        return String(x.id) === String(id)
      })
      names.push(f && f.original_filename ? f.original_filename : id)
    }
    let text = n + ' file' + (n === 1 ? '' : 's') + ' selected'
    if (names.length) text += ': ' + names.join(', ')
    if (n > names.length) text += '…'
    summary.textContent = text
  }

  function saveComposeDraft() {
    try {
      sessionStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({
          caseId: selectedCase && selectedCase.id != null ? String(selectedCase.id) : '',
          attachIds: selectedAttachIds.slice(),
          recipientPick: recipientPick,
          folder: $('folder') ? $('folder').value : '',
          precedent: $('precedent') ? $('precedent').value : '',
          matterMode: $('matter-mode') ? $('matter-mode').value : 'pick',
        }),
      )
    } catch (_) {}
  }

  function readAttachIdsFromStorage(caseId) {
    if (!caseId) return []
    try {
      const raw = sessionStorage.getItem(ATTACH_STORAGE_PREFIX + caseId)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.map(String) : []
    } catch (_) {
      return []
    }
  }

  async function restoreComposeDraft() {
    let draft = null
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY)
      if (raw) draft = JSON.parse(raw)
    } catch (_) {
      return
    }
    if (!draft || !draft.caseId || !allCases.length) return
    const c = allCases.find(function (x) {
      return String(x.id) === String(draft.caseId)
    })
    if (!c) return
    if ($('matter-mode')) $('matter-mode').value = draft.matterMode || 'pick'
    await selectCase(c, { keepAttachIds: true })
    const fromPicker = readAttachIdsFromStorage(String(c.id))
    if (fromPicker.length) selectedAttachIds = fromPicker
    else if (Array.isArray(draft.attachIds)) selectedAttachIds = draft.attachIds.map(String)
    if (draft.recipientPick && !isReplyCompose) recipientPick = draft.recipientPick
    if ($('folder') && draft.folder != null) $('folder').value = draft.folder
    if ($('precedent') && draft.precedent != null) $('precedent').value = draft.precedent
    setRecipientPick(recipientPick)
    updateAttachSummary()
    saveComposeDraft()
  }

  function openAttachPicker() {
    if (!selectedCase || !selectedCase.id) {
      showStatus('msg', 'Select a matter first.', true)
      return
    }
    saveComposeDraft()
    const caseId = String(selectedCase.id)
    const q =
      'caseId=' +
      encodeURIComponent(caseId) +
      '&selected=' +
      encodeURIComponent(selectedAttachIds.join(','))
    window.location.href = './attach-picker.html?' + q
  }

  function updateMatterPickVisibility() {
    const mode = ($('matter-mode') && $('matter-mode').value) || 'pick'
    const pick = $('matter-pick')
    const fields = $('matter-fields')
    const applyBtn = $('btn-apply')
    if (mode === 'none') {
      if (pick) pick.hidden = true
      if (fields) fields.hidden = true
      if (applyBtn) applyBtn.disabled = false
      setCaseSelection('', '')
      selectedCase = null
      return
    }
    if (pick) pick.hidden = false
    if (fields) fields.hidden = !selectedCase
    if (applyBtn) applyBtn.disabled = !selectedCase
  }

  function updateComposeKindUi() {
    const note = $('compose-kind-note')
    const replyNote = $('recipient-reply-note')
    const section = $('recipient-section')
    if (section) section.classList.toggle('is-disabled', isReplyCompose)
    if (note) {
      if (isReplyCompose) {
        note.hidden = false
        note.textContent = 'Reply or forward — merge applies to subject/body; To is unchanged.'
      } else {
        note.hidden = true
      }
    }
    if (replyNote) replyNote.hidden = !isReplyCompose
    if (isReplyCompose) {
      recipientPick = { kind: 'none' }
      setRecipientPick(recipientPick)
    }
  }

  async function selectCase(c, opts) {
    const keepAttach = !!(opts && opts.keepAttachIds)
    selectedCase = c
    if (!keepAttach) {
      selectedAttachIds = []
      try {
        sessionStorage.removeItem(ATTACH_STORAGE_PREFIX + String(c.id))
      } catch (_) {}
    }
    if (!isReplyCompose) recipientPick = { kind: 'none' }
    if ($('matter-mode')) $('matter-mode').value = 'pick'
    setCaseSelection(String(c.id), sh().matterLabel(c))
    updateMatterPickVisibility()
    const token = sh().getToken()
    if (!token) return
    try {
      caseFiles = await apiGet(token, '/cases/' + encodeURIComponent(c.id) + '/files')
      caseContacts = await apiGet(token, '/cases/' + encodeURIComponent(c.id) + '/contacts')
      if (c.matter_sub_type_id) {
        precedents = await apiGet(
          token,
          '/precedents?kind=email&matter_sub_type_id=' + encodeURIComponent(c.matter_sub_type_id),
        )
      } else {
        precedents = await apiGet(token, '/precedents?kind=email')
      }
      fillFolderSelect()
      fillPrecedentSelect()
      renderRecipientPick()
      updateAttachSummary()
      if (!isReplyCompose) setRecipientPick({ kind: 'none' })
      else setRecipientPick(recipientPick)
      saveComposeDraft()
    } catch (e) {
      showStatus('msg', e && e.message ? String(e.message) : 'Could not load matter.', true)
    }
    renderCaseResults()
  }

  function readFormPayload() {
    const folderEl = $('folder')
    const precEl = $('precedent')
    const folder = folderEl ? folderEl.value : ''
    const precedentId = precEl && precEl.value ? precEl.value : null
    let caseContactId = null
    let mergeAllClients = false
    if (!isReplyCompose) {
      if (recipientPick.kind === 'all_clients') {
        mergeAllClients = true
      } else if (recipientPick.kind === 'matter' && recipientPick.matterId) {
        caseContactId = recipientPick.matterId
      }
    }
    return {
      folder: folder,
      precedent_id: precedentId,
      case_contact_id: caseContactId,
      global_contact_id: null,
      precedent_merge_all_clients: mergeAllClients,
      attachment_file_ids: selectedAttachIds.slice(),
    }
  }

  async function syncPendingSend(token, caseId) {
    if (!caseId) {
      await fetch(sh().apiRoot() + '/mail-plugin/pending-send', {
        method: 'DELETE',
        headers: sh().authHeaders(token),
      }).catch(function () {})
      return
    }
    await fetch(sh().apiRoot() + '/mail-plugin/pending-send', {
      method: 'PUT',
      headers: sh().jsonAuthHeaders(token),
      body: JSON.stringify({ case_id: caseId, source_file_id: null, ttl_seconds: 86400 }),
    })
  }

  async function applyToMessage() {
    showStatus('msg', '', true)
    showStatus('ok', '', false)
    const token = sh().getToken()
    if (!token) {
      showStatus('msg', 'Sign in first.', true)
      return
    }
    const mode = ($('matter-mode') && $('matter-mode').value) || 'pick'
    if (mode === 'none') {
      await syncPendingSend(token, null)
      showStatus('ok', 'Matter set to none — sent mail will not be filed.', false)
      return
    }
    if (!selectedCase || !selectedCase.id) {
      showStatus('msg', 'Select a matter first.', true)
      return
    }
    const item = Office.context.mailbox.item
    if (!item) {
      showStatus('msg', 'Open a compose message first.', true)
      return
    }
    const applyBtn = $('btn-apply')
    if (applyBtn) applyBtn.disabled = true
    try {
      const body = readFormPayload()
      const res = await fetch(
        sh().apiRoot() + '/mail-plugin/cases/' + encodeURIComponent(String(selectedCase.id)) + '/compose-bundle',
        { method: 'POST', headers: sh().jsonAuthHeaders(token), body: JSON.stringify(body) },
      )
      const bundle = await res.json().catch(function () {
        return null
      })
      if (!res.ok) {
        const detail = bundle && bundle.detail
        throw new Error(typeof detail === 'string' ? detail : 'Compose bundle failed')
      }
      const added = await applyApi().applyComposeBundle(bundle, { skipTo: isReplyCompose })
      await syncPendingSend(token, String(selectedCase.id))
      let okMsg = 'Applied merge to this message.'
      if (added) okMsg += ' Attached ' + added + ' file(s).'
      okMsg += ' Sent mail will file to this matter.'
      showStatus('ok', okMsg, false)
    } catch (e) {
      showStatus('msg', (e && e.message ? String(e.message) : 'Apply failed') + ' [' + ADDIN_UI_VERSION + ']', true)
    } finally {
      if (applyBtn) applyBtn.disabled = false
      updateMatterPickVisibility()
    }
  }

  async function refreshAuthAndCases() {
    const token = sh().getToken()
    allCases = []
    selectedCase = null
    selectedAttachIds = []
    setCaseSelection('', '')
    updateMatterPickVisibility()
    if ($('case-search')) {
      $('case-search').value = ''
      $('case-search').disabled = !token
    }
    renderCaseResults()

    if (!token) {
      setAuthPanels(false)
      loginShowErr('')
      return
    }
    setAuthPanels(true)
    $('auth-status').textContent = 'Loading…'
    try {
      allCases = await apiGet(token, '/cases')
      let meEmail = ''
      try {
        const me = await apiGet(token, '/auth/me')
        if (me && me.email) meEmail = String(me.email)
      } catch (_) {}
      $('auth-status').textContent =
        (meEmail ? 'Signed in as ' + meEmail + ' · ' : 'Signed in · ') + allCases.length + ' matter(s).'
      await restoreComposeDraft()
    } catch (e) {
      const msg = e && e.message ? String(e.message) : 'Failed to load matters.'
      showStatus('msg', msg, true)
      if (msg === '401 Unauthorized') {
        await sh().persistTokenAsync('')
        setAuthPanels(false)
      }
    }
  }

  async function detectComposeKind() {
    try {
      const item = Office.context.mailbox.item
      if (!item) return
      const ct = await applyApi().getComposeTypeAsync(item)
      isReplyCompose = ct === 'reply' || ct === 'forward'
      updateComposeKindUi()
    } catch (_) {
      isReplyCompose = false
    }
  }

  Office.onReady(function () {
    const signIn = $('btn-sign-in')
    if (signIn) signIn.onclick = function () {
      void submitLogin()
    }
    const loginEmail = $('login-email')
    if (loginEmail) {
      loginEmail.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') void submitLogin()
      })
    }
    const loginPw = $('login-password')
    if (loginPw) {
      loginPw.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') void submitLogin()
      })
    }
    $('btn-logout').onclick = function () {
      void (async function () {
        try {
          await sh().persistTokenAsync('')
          selectedCase = null
          await refreshAuthAndCases()
        } catch (e) {
          showStatus('msg', e && e.message ? String(e.message) : 'Could not sign out.', true)
        }
      })()
    }
    const matterMode = $('matter-mode')
    if (matterMode) {
      matterMode.onchange = function () {
        updateMatterPickVisibility()
        if (matterMode.value === 'pick' && $('case-search')) {
          $('case-search').focus()
        }
      }
    }
    const searchInput = $('case-search')
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        renderCaseResults()
      })
    }
    $('btn-apply').onclick = function () {
      void applyToMessage()
    }
    const attachBtn = $('btn-attach-from-file')
    if (attachBtn) {
      attachBtn.onclick = function () {
        openAttachPicker()
      }
    }

    void (async function () {
      await detectComposeKind()
      await refreshAuthAndCases()
    })()
  })
})()
