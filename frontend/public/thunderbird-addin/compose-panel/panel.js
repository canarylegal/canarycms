/* global messenger, browser */
'use strict'
;(function () {
  const sh = () => globalThis.canaryShared
  const cs = () => globalThis.canaryComposeStore
  const attachUi = () => globalThis.canaryComposeAttachUi

  let composeTabId = null
  let allCases = []
  let caseFiles = []
  let caseContacts = []
  let precedents = []
  let selectedCase = null
  let attachBrowseFolder = ''
  let selectedAttachIds = []
  /** User changed Matter dropdown; do not overwrite from background prefill/store sync. */
  let userMatterModeDirty = false
  /** @type {{ kind: 'none'|'all_clients'|'matter', matterId?: string, label?: string }} */
  let recipientPick = { kind: 'none' }
  /** Reply/forward — do not change To or enable recipient picker. */
  let isReplyCompose = false

  function sendRuntimeMessage(ext, payload) {
    return new Promise(function (resolve) {
      if (!ext.runtime || !ext.runtime.sendMessage) {
        resolve({ ok: false, detail: 'Runtime messaging not available.' })
        return
      }
      ext.runtime.sendMessage(payload, function (resp) {
        if (ext.runtime.lastError) {
          resolve({ ok: false, detail: String(ext.runtime.lastError.message) })
          return
        }
        resolve(resp || { ok: false })
      })
    })
  }

  function $(id) {
    return document.getElementById(id)
  }

  function out(text, isErr) {
    const el = $('out')
    if (!el) return
    el.className = isErr ? 'err' : text ? 'ok' : ''
    el.textContent = text || ''
  }

  function composeTabIdFromUrl() {
    try {
      const params = new URLSearchParams(String(globalThis.location.search || ''))
      const tid = params.get('composeTabId')
      if (tid == null || String(tid).trim() === '') return null
      const n = Number(tid)
      return Number.isFinite(n) ? n : tid
    } catch (_) {
      return null
    }
  }

  async function resolveComposeTabId(ext) {
    const fromUrl = composeTabIdFromUrl()
    if (fromUrl != null) return fromUrl
    const panelTab = await sh().getComposePanelTabId(ext)
    if (panelTab != null) {
      if (ext.compose && typeof ext.compose.getComposeDetails === 'function') {
        try {
          await ext.compose.getComposeDetails(panelTab)
          return panelTab
        } catch (_) {
          /* stale session tab id */
        }
      } else {
        return panelTab
      }
    }
    if (ext.tabs && typeof ext.tabs.getCurrent === 'function') {
      try {
        const cur = await ext.tabs.getCurrent()
        if (cur && cur.id != null && ext.compose && typeof ext.compose.getComposeDetails === 'function') {
          try {
            await ext.compose.getComposeDetails(cur.id)
            return cur.id
          } catch (_) {
            /* not a compose tab */
          }
        }
      } catch (_) {
        /* ignore */
      }
    }
    let id = await cs().getActiveComposeTab(ext)
    if (id != null) return id
    if (ext.tabs && ext.tabs.query) {
      try {
        const composeTabs = await ext.tabs.query({ type: 'messageCompose' })
        if (composeTabs && composeTabs.length) {
          let pick = null
          for (let i = 0; i < composeTabs.length; i++) {
            if (composeTabs[i].active) {
              pick = composeTabs[i]
              break
            }
          }
          if (!pick) pick = composeTabs[composeTabs.length - 1]
          if (pick && pick.id != null) return pick.id
        }
      } catch (_) {
        /* ignore */
      }
    }
    return null
  }

  async function loadAuth(ext) {
    const { jwt, origin } = await sh().getStoredAuth(ext)
    if (!jwt || !origin) throw new Error('Sign in via Canary toolbar (Server & sign-in).')
    return { jwt, origin }
  }

  function authErrorHint(err) {
    const msg = err && err.message ? String(err.message) : ''
    if (sh().isAuthSessionErrorMessage(msg)) {
      return 'Session expired or the Canary site changed — open Server & sign-in on the toolbar and sign in again.'
    }
    return msg || 'Request failed.'
  }

  async function apiGet(ext, jwt, origin, path) {
    const res = await fetch(sh().apiRoot(origin) + path, { headers: sh().authHeaders(jwt) })
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      const detail = body && body.detail
      const msg = typeof detail === 'string' ? detail : 'Request failed (' + res.status + ')'
      if (res.status === 401 && sh().isAuthSessionErrorMessage(msg)) {
        await sh().clearStoredJwt(ext)
      }
      throw new Error(msg)
    }
    return body
  }

  function renderCaseResults() {
    const box = $('case-results')
    const input = $('case-search')
    if (!box || !input) return
    const q = String(input.value || '').trim().toLowerCase()
    box.innerHTML = ''
    if (!q) {
      box.hidden = true
      return
    }
    const matches = allCases.filter((c) => sh().matterLabel(c).toLowerCase().includes(q))
    if (!matches.length) {
      box.innerHTML =
        '<div class="muted" style="padding:6px">No matches.</div>'
      box.hidden = false
      return
    }
    for (const c of matches.slice(0, 40)) {
      const id = String(c.id)
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'case-result-row' + (selectedCase && String(selectedCase.id) === id ? ' is-selected' : '')
      btn.textContent = sh().matterLabel(c)
      btn.onclick = () => {
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
      box.querySelectorAll('[data-recipient]').forEach((btn) => {
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
    noneBtn.onclick = () => {
      setRecipientPick({ kind: 'none' })
      void persistState(sh().getGecko())
    }
    box.appendChild(noneBtn)

    const allBtn = document.createElement('button')
    allBtn.type = 'button'
    allBtn.className = 'case-result-row'
    allBtn.dataset.recipient = 'all_clients'
    allBtn.textContent = 'All clients (merge only)'
    allBtn.onclick = () => {
      setRecipientPick({ kind: 'all_clients' })
      void persistState(sh().getGecko())
    }
    box.appendChild(allBtn)

    if (!caseContacts.length) {
      const hint = document.createElement('div')
      hint.className = 'muted'
      hint.style.padding = '6px'
      hint.textContent = 'No matter contacts on this case — add contacts in Canary first.'
      box.appendChild(hint)
    }
    for (const cc of caseContacts) {
      const id = String(cc.id)
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'case-result-row'
      btn.dataset.recipient = 'matter:' + id
      btn.textContent = contactLabel(cc)
      btn.onclick = () => {
        setRecipientPick({ kind: 'matter', matterId: id, label: contactLabel(cc) })
        void persistState(sh().getGecko())
      }
      box.appendChild(btn)
    }
    setRecipientPick(recipientPick)
  }

  function fillFolderSelect() {
    const sel = $('folder')
    const ui = attachUi()
    if (!sel || !ui) return
    const prev = sel.value
    sel.innerHTML = ''
    const o0 = document.createElement('option')
    o0.value = ''
    o0.textContent = 'None (matter root)'
    sel.appendChild(o0)
    for (const path of ui.collectAllFolderPaths(caseFiles)) {
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

  function updateAttachSummary() {
    const section = $('attach-section')
    const summary = $('attach-selected-summary')
    const btn = $('btn-attach-from-file')
    if (!selectedCase) {
      if (section) section.hidden = true
      return
    }
    if (section) section.hidden = false
    if (btn) btn.disabled = false
    if (!summary) return
    const n = selectedAttachIds.length
    if (n === 0) {
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

  async function openAttachPickerWindow() {
    const caseId =
      selectedCase && selectedCase.id != null
        ? String(selectedCase.id)
        : (await readFormStateFromStore(sh().getGecko())).caseId
    if (!caseId || composeTabId == null) {
      out('Select a matter first.', true)
      return
    }
    const ext = sh().getGecko()
    const r = await sendRuntimeMessage(ext, {
      type: 'canary-open-attach-picker',
      caseId: caseId,
      composeTabId: composeTabId,
      selectedIds: selectedAttachIds,
    })
    if (!r || !r.ok) {
      out((r && r.detail) || 'Could not open attach picker.', true)
    }
  }

  async function loadAttachSelectionFromStore(ext) {
    if (composeTabId == null) {
      selectedAttachIds = []
      return
    }
    const st = await cs().getTabState(ext, composeTabId)
    selectedAttachIds = (st && st.attachmentFileIds) || []
  }

  async function selectCase(c) {
    userMatterModeDirty = true
    selectedCase = c
    attachBrowseFolder = ''
    const sel = $('case-selected')
    if (sel) sel.textContent = 'Selected: ' + sh().matterLabel(c)
    if ($('matter-mode')) $('matter-mode').value = 'pick'
    updateMatterPickVisibility()
    const ext = sh().getGecko()
    const { jwt, origin } = await loadAuth(ext)
    caseFiles = await apiGet(ext, jwt, origin, '/cases/' + encodeURIComponent(c.id) + '/files')
    caseContacts = await apiGet(ext, jwt, origin, '/cases/' + encodeURIComponent(c.id) + '/contacts')
    if (c.matter_sub_type_id) {
      precedents = await apiGet(
        ext,
        jwt,
        origin,
        '/precedents?kind=email&matter_sub_type_id=' + encodeURIComponent(c.matter_sub_type_id),
      )
    } else {
      precedents = await apiGet(ext, jwt, origin, '/precedents?kind=email')
    }
    fillMatterFields()
    fillFolderSelect()
    renderRecipientPick()
    await loadAttachSelectionFromStore(ext)
    updateMatterPickVisibility()
    updateAttachSummary()
    await persistState(ext)
  }

  function fillMatterFields() {
    const prec = $('precedent')
    if (prec) {
      prec.innerHTML = '<option value="">None</option>'
      for (const p of precedents) {
        const o = document.createElement('option')
        o.value = String(p.id)
        o.textContent = p.name || p.reference || p.id
        prec.appendChild(o)
      }
    }
  }

  function readFormState() {
    const mode = ($('matter-mode') && $('matter-mode').value) || 'none'
    let caseContactId = null
    let mergeAll = false
    if (recipientPick.kind === 'all_clients') mergeAll = true
    else if (recipientPick.kind === 'matter' && recipientPick.matterId) caseContactId = recipientPick.matterId
    return {
      caseId: mode === 'pick' && selectedCase ? String(selectedCase.id) : null,
      folder: ($('folder') && $('folder').value) || '',
      parentFileId: null,
      precedentId: ($('precedent') && $('precedent').value) || null,
      caseContactId,
      globalContactId: null,
      mergeAllClients: mergeAll,
      attachmentFileIds: selectedAttachIds.slice(),
    }
  }

  /** Merge background prefill (tab store) with visible form — prefill often sets caseId before selectedCase exists. */
  async function readFormStateFromStore(ext) {
    const base = readFormState()
    if (composeTabId == null) return base
    const st = await cs().getTabState(ext, composeTabId)
    const mode = ($('matter-mode') && $('matter-mode').value) || 'none'
    if (mode === 'pick' && st.caseId && !base.caseId) {
      base.caseId = String(st.caseId)
    }
    if (st.folder) base.folder = st.folder
    if (st.parentFileId) base.parentFileId = st.parentFileId
    if (st.precedentId) base.precedentId = st.precedentId
    if (st.caseContactId) base.caseContactId = st.caseContactId
    if (st.mergeAllClients) base.mergeAllClients = true
    if (!base.attachmentFileIds.length && st.attachmentFileIds && st.attachmentFileIds.length) {
      base.attachmentFileIds = st.attachmentFileIds
    }
    return base
  }

  async function persistState(ext) {
    if (composeTabId == null) return
    const ui = readFormState()
    const prev = await cs().getTabState(ext, composeTabId)
    const mode = ($('matter-mode') && $('matter-mode').value) || 'none'
    const patch = {
      folder: ui.folder,
      precedentId: ui.precedentId,
      caseContactId: ui.caseContactId,
      globalContactId: null,
      mergeAllClients: ui.mergeAllClients,
      attachmentFileIds: ui.attachmentFileIds,
    }
    if (mode === 'none') {
      patch.caseId = null
      patch.parentFileId = null
      patch.userOverridden = true
      patch.prefilledFromReply = false
    } else if (ui.caseId) {
      patch.caseId = ui.caseId
      patch.userOverridden = false
      patch.prefilledFromReply = false
      patch.prefilledFromPending = false
    } else if (prev.caseId) {
      patch.caseId = prev.caseId
      patch.parentFileId = prev.parentFileId
      patch.userOverridden = false
    }
    await cs().setTabState(ext, composeTabId, patch)
  }

  function caseObjectFromStore(st) {
    if (!st || !st.caseId) return null
    const found = allCases.find((x) => String(x.id) === String(st.caseId))
    if (found) return found
    return {
      id: st.caseId,
      case_number: st.prefilledCaseNumber || '',
      client_name: st.prefilledClientName || '',
      matter_description: st.prefilledMatterTitle || '',
    }
  }

  async function maybeAutoApplyFromStore() {
    /* Reply prefill disabled — user must click Apply to message after choosing a matter. */
  }

  function updatePrefillHint(st) {
    const hint = $('prefill-hint')
    const statusEl = $('prefill-status')
    const s = st && st.prefillStatus ? String(st.prefillStatus) : ''
    const isReplyHint = s === 'reply-manual' || s.indexOf('waiting-type') === 0
    if (hint) hint.hidden = !isReplyHint
    if (!statusEl) return
    if (s === 'not-signed-in') {
      statusEl.hidden = false
      statusEl.textContent =
        'Sign in via Canary toolbar (Server & sign-in) to file this message to a matter.'
    } else if (s.indexOf('waiting-type') === 0) {
      statusEl.hidden = false
      statusEl.textContent = 'Waiting for Thunderbird to finish opening the reply…'
    } else if (s === 'reply-manual') {
      statusEl.hidden = true
      statusEl.textContent = ''
    } else if (s.indexOf('not-reply') === 0) {
      statusEl.hidden = true
      statusEl.textContent = ''
    } else if (s) {
      statusEl.hidden = true
      statusEl.textContent = ''
    } else {
      statusEl.hidden = true
      statusEl.textContent = ''
    }
  }

  function updateMatterPickVisibility() {
    const mode = ($('matter-mode') && $('matter-mode').value) || 'none'
    const pick = $('matter-pick')
    const fields = $('matter-fields')
    if (pick) pick.hidden = mode !== 'pick'
    if (fields) fields.hidden = mode !== 'pick' || !selectedCase
  }

  async function clearMatterBecauseUserChoseNone() {
    selectedCase = null
    attachBrowseFolder = ''
    selectedAttachIds = []
    recipientPick = { kind: 'none' }
    const section = $('attach-section')
    if (section) section.hidden = true
    updatePrefillHint(null)
    updateMatterPickVisibility()
    const ext = sh().getGecko()
    if (composeTabId == null) return
    try {
      const { jwt, origin } = await loadAuth(ext)
      await sh().syncPendingSend(jwt, origin, null, null)
      await cs().setTabState(
        ext,
        composeTabId,
        Object.assign(cs().blankState(), { userOverridden: true }),
      )
    } catch (_) {
      await cs().setTabState(ext, composeTabId, Object.assign(cs().blankState(), { userOverridden: true }))
    }
  }

  async function applyCaseFromStore(ext, st) {
    const c = caseObjectFromStore(st)
    if (c) await selectCase(c)
    await cs().setTabState(ext, composeTabId, {
      parentFileId: st.parentFileId,
      folder: st.folder || '',
      prefilledFromReply: st.prefilledFromReply,
      prefilledFromPending: st.prefilledFromPending,
      mergeAllClients: st.mergeAllClients,
      userOverridden: false,
    })
    if ($('folder')) {
      fillFolderSelect()
      $('folder').value = st.folder || ''
    }
    if ($('precedent') && st.precedentId) $('precedent').value = st.precedentId
    if (st.mergeAllClients || st.composeAutoApplied || st.prefilledFromReply) {
      setRecipientPick({ kind: 'all_clients' })
    } else if (st.caseContactId) {
      const cc = caseContacts.find((x) => String(x.id) === String(st.caseContactId))
      setRecipientPick({
        kind: 'matter',
        matterId: st.caseContactId,
        label: cc ? contactLabel(cc) : st.caseContactId,
      })
    } else {
      setRecipientPick({ kind: 'none' })
    }
    renderRecipientPick()
    selectedAttachIds = (st && st.attachmentFileIds) || []
    updateAttachSummary()
    await maybeAutoApplyFromStore(ext)
  }

  function shouldApplyStoredMatter() {
    return false
  }

  async function detectReplyCompose(ext) {
    if (composeTabId == null || !ext.compose || typeof ext.compose.getComposeDetails !== 'function') {
      return false
    }
    try {
      const details = await ext.compose.getComposeDetails(composeTabId)
      const t = details && details.type ? String(details.type).toLowerCase() : ''
      if (t === 'new' || t === 'draft') return false
      return (
        t === 'reply' ||
        t === 'forward' ||
        t.indexOf('reply') >= 0 ||
        t.indexOf('forward') >= 0
      )
    } catch (_) {
      return false
    }
  }

  function updateComposeKindUi() {
    const section = $('recipient-section')
    if (section) section.classList.toggle('is-disabled', isReplyCompose)
    const replyNote = $('recipient-reply-note')
    const newNote = $('recipient-new-note')
    if (replyNote) replyNote.hidden = !isReplyCompose
    if (newNote) newNote.hidden = isReplyCompose
  }

  async function closeComposePanelAfterDone(ext) {
    await sh().closeExtensionWindow(ext)
  }

  async function ensureNewComposeDefaults(ext) {
    if (composeTabId == null || !ext.compose || typeof ext.compose.getComposeDetails !== 'function') {
      return
    }
    try {
      const details = await ext.compose.getComposeDetails(composeTabId)
      const t = details && details.type ? String(details.type).toLowerCase() : ''
      if (t !== 'new' && t !== 'draft') return
      userMatterModeDirty = false
      selectedCase = null
      if ($('matter-mode')) $('matter-mode').value = 'pick'
      const search = $('case-search')
      if (search) search.value = ''
      const box = $('case-results')
      if (box) {
        box.hidden = true
        box.innerHTML = ''
      }
      updateMatterPickVisibility()
      updatePrefillHint(null)
    } catch (_) {
      /* ignore */
    }
  }

  async function restoreState(ext, options) {
    if (composeTabId == null) return
    const st = await cs().getTabState(ext, composeTabId)
    updatePrefillHint(st)
    selectedAttachIds = (st && st.attachmentFileIds) || []

    const modeEl = $('matter-mode')

    if (!userMatterModeDirty && modeEl) {
      if (st.userOverridden) {
        modeEl.value = 'none'
      } else if (shouldApplyStoredMatter(st)) {
        modeEl.value = 'pick'
      } else {
        modeEl.value = 'pick'
      }
      updateMatterPickVisibility()
    }

    const uiMode = modeEl ? modeEl.value : 'pick'

    if (uiMode === 'none') {
      selectedCase = null
      updateMatterPickVisibility()
      updateAttachSummary()
      return
    }

    if (uiMode === 'pick' && shouldApplyStoredMatter(st)) {
      await applyCaseFromStore(ext, st)
      return
    }

    if (uiMode === 'pick' && selectedCase) {
      updateMatterPickVisibility()
      updateAttachSummary()
      return
    }

    if (uiMode === 'pick') {
      const search = $('case-search')
      const keepSearch =
        search &&
        (document.activeElement === search ||
          userMatterModeDirty ||
          String(search.value || '').trim().length > 0)
      if (search && !keepSearch) search.value = ''
      renderCaseResults()
      updateMatterPickVisibility()
    }
    updateAttachSummary()
  }

  async function updateSetupButtonVisibility(ext) {
    const btn = $('btn-setup')
    if (!btn) return
    try {
      const { jwt, origin } = await sh().getStoredAuth(ext)
      btn.hidden = !!(jwt && origin)
    } catch (_) {
      btn.hidden = false
    }
  }

  async function applyAttachmentsFromCanary(ext) {
    if (composeTabId == null || !globalThis.canaryApplyComposeAttachments) return
    const form = await readFormStateFromStore(ext)
    if (!form.caseId || !form.attachmentFileIds || !form.attachmentFileIds.length) return
    try {
      const { jwt, origin } = await loadAuth(ext)
      const body = {
        folder: form.folder || '',
        precedent_id: form.precedentId || null,
        case_contact_id: form.caseContactId || null,
        global_contact_id: null,
        precedent_merge_all_clients: form.mergeAllClients,
        attachment_file_ids: form.attachmentFileIds,
      }
      const bundle = await fetch(
        sh().apiRoot(origin) + '/mail-plugin/cases/' + encodeURIComponent(form.caseId) + '/compose-bundle',
        { method: 'POST', headers: sh().jsonAuthHeaders(jwt), body: JSON.stringify(body) },
      ).then(async function (res) {
        const data = await res.json().catch(function () {
          return null
        })
        if (!res.ok) {
          const detail = data && data.detail
          throw new Error(typeof detail === 'string' ? detail : 'Compose bundle failed')
        }
        return data
      })
      await globalThis.canaryApplyComposeAttachments(ext, composeTabId, bundle)
      out('Attached ' + form.attachmentFileIds.length + ' file(s) from Canary.', false)
    } catch (e) {
      out(authErrorHint(e), true)
    }
  }

  function startPrefillSync() {
    /* Automatic reply prefill disabled — no background sync of matter selection. */
  }

  function onMatterModeChange() {
    userMatterModeDirty = true
    const mode = ($('matter-mode') && $('matter-mode').value) || 'none'
    updateMatterPickVisibility()
    void (async function () {
      const ext = sh().getGecko()
      if (mode === 'none') {
        await clearMatterBecauseUserChoseNone()
        out('Matter set to none — sent mail will not be filed.', false)
        return
      }
      const search = $('case-search')
      if (search) {
        search.value = ''
        search.focus()
      }
      renderCaseResults()
      if (!allCases.length) {
        out('No matters loaded — sign in via Server & sign-in.', true)
      } else {
        out('Type in Search matters to find a matter.', false)
      }
    })()
  }

  async function main() {
    const ext = sh().getGecko()
    if (!ext) {
      out('Extension APIs not available.', true)
      return
    }
    sh().wirePopoutCloseButton('btn-close')
    composeTabId = await resolveComposeTabId(ext)
    if (composeTabId != null) await cs().setActiveComposeTab(ext, composeTabId)
    isReplyCompose = await detectReplyCompose(ext)
    updateComposeKindUi()

    try {
      const { jwt, origin } = await loadAuth(ext)
      allCases = await apiGet(ext, jwt, origin, '/cases')
      out('', false)
      await updateSetupButtonVisibility(ext)
    } catch (e) {
      out(authErrorHint(e), true)
      await updateSetupButtonVisibility(ext)
    }

    function withExt(fn) {
      return function () {
        void fn(sh().getGecko())
      }
    }
    $('matter-mode').addEventListener('change', onMatterModeChange)
    $('case-search').addEventListener('input', function () {
      userMatterModeDirty = true
      renderCaseResults()
    })
    ;['folder', 'precedent'].forEach((id) => {
      const el = $(id)
      if (el) el.addEventListener('change', withExt(persistState))
    })

    $('btn-setup').addEventListener('click', () => {
      void ext.runtime.sendMessage({ type: 'canary-open-companion' })
    })

    const btnAttach = $('btn-attach-from-file')
    if (btnAttach) {
      btnAttach.addEventListener('click', () => {
        void openAttachPickerWindow()
      })
    }

    $('btn-apply').addEventListener('click', () => {
      void (async function () {
        out('Applying…', false)
        $('btn-apply').disabled = true
        try {
          if (composeTabId == null) throw new Error('No compose tab found. Click in the message body, then reopen Canary.')
          const { jwt, origin } = await loadAuth(ext)
          const form = await readFormStateFromStore(ext)
          if (!form.caseId) {
            await sh().syncPendingSend(jwt, origin, null, null)
            out('Matter set to none — sent mail will not be filed.', false)
            await closeComposePanelAfterDone(ext)
            return
          }
          const body = {
            folder: form.folder,
            precedent_id: form.precedentId || null,
            case_contact_id: form.caseContactId || null,
            global_contact_id: null,
            precedent_merge_all_clients: form.mergeAllClients,
            attachment_file_ids: form.attachmentFileIds,
          }
          const bundle = await fetch(
            sh().apiRoot(origin) + '/mail-plugin/cases/' + encodeURIComponent(form.caseId) + '/compose-bundle',
            { method: 'POST', headers: sh().jsonAuthHeaders(jwt), body: JSON.stringify(body) },
          ).then(async (res) => {
            const data = await res.json().catch(() => null)
            if (!res.ok) {
              const detail = data && data.detail
              throw new Error(typeof detail === 'string' ? detail : 'Compose bundle failed')
            }
            return data
          })
          await globalThis.canaryApplyComposeBundle(ext, composeTabId, bundle, {
            skipTo: isReplyCompose,
          })
          let sourceFileId = form.parentFileId || null
          let filedIncoming = false
          if (isReplyCompose) {
            const relatedId = await sh().resolveRelatedMessageIdForCompose(ext, composeTabId)
            if (relatedId != null) {
              const filed = await sh().fileTbMessageById(ext, jwt, origin, form.caseId, relatedId, {
                folder: form.folder,
                tag: true,
              })
              if (filed && filed.fileId) {
                sourceFileId = String(filed.fileId)
                filedIncoming = true
              }
            }
          }
          await cs().setTabState(ext, composeTabId, {
            caseId: form.caseId,
            folder: form.folder,
            parentFileId: null,
            precedentId: form.precedentId,
            caseContactId: isReplyCompose ? null : form.caseContactId,
            mergeAllClients: form.mergeAllClients,
            attachmentFileIds: form.attachmentFileIds,
            composeAutoApplied: true,
          })
          await sh().syncPendingSend(jwt, origin, form.caseId, sourceFileId || null)
          if (filedIncoming) {
            out(
              'Applied. Incoming message saved to the matter and tagged. Your sent reply will file to the matter when you send.',
              false,
            )
          } else if (isReplyCompose) {
            out(
              'Applied to compose. Could not find the original message to file — your sent reply will still file when you send.',
              false,
            )
          } else {
            out('Applied. Your message will file to the matter when you send.', false)
          }
          await closeComposePanelAfterDone(ext)
        } catch (e) {
          out(authErrorHint(e), true)
        } finally {
          $('btn-apply').disabled = false
        }
      })()
    })

    globalThis.addEventListener('focus', function () {
      void (async function () {
        if (composeTabId != null) {
          const st = await cs().getTabState(ext, composeTabId)
          selectedAttachIds = (st && st.attachmentFileIds) || []
          updateAttachSummary()
          if (!userMatterModeDirty && !selectedCase) {
            await restoreState(ext)
          }
        }
      })()
    })

    if (ext.storage && ext.storage.onChanged) {
      ext.storage.onChanged.addListener(function (changes, area) {
        if (area !== 'local') return
        if (changes.canary_jwt || changes.canaryApiOrigin) {
          void updateSetupButtonVisibility(ext)
        }
        if (!changes.canary_compose_tab_state || composeTabId == null) return
        void (async function () {
          const st = await cs().getTabState(ext, composeTabId)
          if (userMatterModeDirty || (selectedCase && st.caseId && String(selectedCase.id) === String(st.caseId))) {
            await loadAttachSelectionFromStore(ext)
            updateAttachSummary()
            return
          }
          await restoreState(ext, { fromStorage: true })
        })()
      })
    }

    await ensureNewComposeDefaults(ext)
    await restoreState(ext)
    startPrefillSync()
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', main)
  } else {
    main()
  }
})()
