/* global Office */
;(function () {
  'use strict'

  const sh = function () {
    return globalThis.canaryOutlookShared
  }
  const ui = function () {
    return globalThis.canaryOutlookAttachUi
  }
  const STORAGE_PREFIX = 'canary_outlook_attach_'

  let caseId = ''
  let browseFolder = ''
  let caseFiles = []
  let selectedIds = []

  function $(id) {
    return document.getElementById(id)
  }

  function params() {
    try {
      return new URLSearchParams(String(window.location.search || ''))
    } catch (_) {
      return new URLSearchParams()
    }
  }

  function showErr(msg) {
    const el = $('err')
    if (!el) return
    el.style.display = msg ? 'block' : 'none'
    el.textContent = msg || ''
  }

  function updateFooter() {
    const line = $('selection-line')
    const btn = $('btn-done')
    const n = selectedIds.length
    const max = ui().MAX_ATTACH
    if (line) {
      line.textContent =
        n === 0
          ? 'Click files to select (up to ' + max + ').'
          : n + ' file' + (n === 1 ? '' : 's') + ' selected'
    }
    if (btn) btn.disabled = false
  }

  function normalizeCaseFiles(body) {
    if (Array.isArray(body)) return body
    if (body && Array.isArray(body.files)) return body.files
    return []
  }

  function renderList() {
    const root = $('picker-root')
    if (!root || !ui()) return
    ui().renderAttachPicker(root, {
      files: caseFiles,
      selectedIds: selectedIds,
      browseFolder: browseFolder,
      onBrowseFolder: function (path) {
        browseFolder = path
        renderList()
      },
      onSelectionChange: function (ids) {
        selectedIds = ids
        updateFooter()
      },
      onStatus: function (text, isErr) {
        if (isErr) showErr(text)
        else showErr('')
      },
    })
  }

  function returnToComposePane() {
    try {
      sessionStorage.setItem(STORAGE_PREFIX + caseId, JSON.stringify(selectedIds))
    } catch (_) {}
    window.location.href = './compose-pane.html'
  }

  async function loadFiles() {
    const token = sh().getToken()
    if (!token) throw new Error('Sign in via Compose from matter first.')
    const body = await fetch(sh().apiRoot() + '/cases/' + encodeURIComponent(caseId) + '/files', {
      headers: sh().authHeaders(token),
    }).then(async function (res) {
      const data = await res.json().catch(function () {
        return null
      })
      if (!res.ok) throw new Error('Could not load matter files.')
      return data
    })
    caseFiles = normalizeCaseFiles(body)
    const matterLine = $('matter-line')
    if (matterLine) {
      matterLine.textContent =
        caseFiles.length === 0
          ? 'No files in this matter'
          : caseFiles.length + ' file' + (caseFiles.length === 1 ? '' : 's') + ' in matter'
    }
  }

  Office.onReady(function () {
    const p = params()
    caseId = String(p.get('caseId') || '').trim()
    const sel = String(p.get('selected') || '').trim()
    if (sel) {
      selectedIds = sel
        .split(',')
        .map(function (s) {
          return s.trim()
        })
        .filter(Boolean)
    }

    $('btn-cancel').onclick = returnToComposePane
    $('btn-done').onclick = returnToComposePane

    if (!caseId) {
      showErr('No matter specified.')
      return
    }

    const root = $('picker-root')
    if (root) root.innerHTML = '<div class="picker-empty">Loading files…</div>'

    void (async function () {
      try {
        await loadFiles()
        showErr('')
        updateFooter()
        renderList()
      } catch (e) {
        if (root) root.innerHTML = ''
        showErr(e && e.message ? String(e.message) : 'Failed to load files.')
      }
    })()
  })
})()
