/* global messenger, browser */
'use strict'
;(function () {
  const sh = () => globalThis.canaryShared
  const cs = () => globalThis.canaryComposeStore
  const ui = () => globalThis.canaryComposeAttachUi

  let caseId = ''
  let composeTabId = null
  let browseFolder = ''
  let caseFiles = []
  let selectedIds = []

  function $(id) {
    return document.getElementById(id)
  }

  function params() {
    try {
      return new URLSearchParams(String(globalThis.location.search || ''))
    } catch (_) {
      return new URLSearchParams()
    }
  }

  function showErr(msg) {
    const el = $('err')
    if (!el) return
    if (msg) {
      el.hidden = false
      el.textContent = msg
    } else {
      el.hidden = true
      el.textContent = ''
    }
  }

  function updateFooter() {
    const line = $('selection-line')
    const btn = $('btn-attach')
    const n = selectedIds.length
    const max = ui().MAX_ATTACH
    if (line) {
      line.textContent =
        n === 0
          ? 'Click files to select (up to ' + max + ').'
          : n + ' file' + (n === 1 ? '' : 's') + ' selected'
    }
    if (btn) btn.disabled = n === 0
  }

  function renderCrumbs(root) {
    const crumbs = document.createElement('div')
    crumbs.className = 'attach-crumbs'
    const home = document.createElement('button')
    home.type = 'button'
    home.className = 'attach-crumb'
    home.textContent = 'All files'
    home.onclick = function () {
      browseFolder = ''
      renderList()
    }
    crumbs.appendChild(home)
    const parts = String(browseFolder || '')
      .split('/')
      .filter(Boolean)
    let acc = ''
    for (let i = 0; i < parts.length; i++) {
      const sep = document.createElement('span')
      sep.textContent = ' / '
      sep.style.color = '#94a3b8'
      crumbs.appendChild(sep)
      acc = acc ? acc + '/' + parts[i] : parts[i]
      const seg = acc
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'attach-crumb'
      btn.textContent = ui().decodeFolderSegment(parts[i])
      btn.onclick = function () {
        browseFolder = seg
        renderList()
      }
      crumbs.appendChild(btn)
    }
    root.appendChild(crumbs)
  }

  function toggleFile(id) {
    const sid = String(id)
    const idx = selectedIds.indexOf(sid)
    if (idx >= 0) {
      selectedIds = selectedIds.filter(function (x) {
        return x !== sid
      })
    } else {
      if (selectedIds.length >= ui().MAX_ATTACH) {
        showErr('At most ' + ui().MAX_ATTACH + ' attachments.')
        return
      }
      selectedIds = selectedIds.concat([sid])
      showErr('')
    }
    updateFooter()
    renderList()
  }

  function normalizeCaseFiles(body) {
    if (Array.isArray(body)) return body
    if (body && Array.isArray(body.files)) return body.files
    return []
  }

  function renderList() {
    const root = $('picker-root')
    if (!root || !ui()) return
    root.innerHTML = ''
    renderCrumbs(root)

    const folders = ui().childFolders(caseFiles, browseFolder)
    let docs = ui().filesInBrowseFolder(caseFiles, browseFolder)

    if (!folders.length && !docs.length && browseFolder === '') {
      docs = ui().allAttachableFiles(caseFiles)
      if (docs.length) {
        const hint = document.createElement('div')
        hint.className = 'picker-empty'
        hint.textContent = 'Open a folder above, or pick a file below:'
        root.appendChild(hint)
      }
    }

    if (!folders.length && !docs.length) {
      const empty = document.createElement('div')
      empty.className = 'picker-empty'
      empty.textContent = 'No attachable files in this matter.'
      root.appendChild(empty)
      return
    }

    for (let i = 0; i < folders.length; i++) {
      const name = folders[i]
      const next = browseFolder ? browseFolder + '/' + name : name
      const row = document.createElement('button')
      row.type = 'button'
      row.className = 'tb-list-row tb-list-row--folder'
      row.innerHTML =
        '<span class="tb-row-icon" aria-hidden="true">📁</span>' +
        '<span class="tb-row-label">' +
        ui().decodeFolderSegment(name) +
        '</span>'
      row.onclick = function () {
        browseFolder = next
        renderList()
      }
      root.appendChild(row)
    }

    for (let j = 0; j < docs.length; j++) {
      const f = docs[j]
      const id = String(f.id)
      const row = document.createElement('button')
      row.type = 'button'
      row.className =
        'tb-list-row tb-list-row--file' + (selectedIds.indexOf(id) >= 0 ? ' is-selected' : '')
      const folderHint = f.folder_path ? ' (' + String(f.folder_path) + ')' : ''
      row.innerHTML =
        '<span class="tb-row-icon" aria-hidden="true">📄</span>' +
        '<span class="tb-row-label">' +
        (f.original_filename || id) +
        folderHint +
        '</span>' +
        '<span class="tb-row-check" aria-hidden="true">✓</span>'
      row.onclick = function () {
        toggleFile(id)
      }
      root.appendChild(row)
    }
  }

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

  async function confirmAttach() {
    const ext = sh().getGecko()
    if (!ext || composeTabId == null) return
    await cs().setTabState(ext, composeTabId, { attachmentFileIds: selectedIds.slice() })
    const r = await sendRuntimeMessage(ext, {
      type: 'canary-apply-compose-attachments',
      composeTabId: composeTabId,
      caseId: caseId,
    })
    if (!r || !r.ok) {
      showErr((r && r.detail) || 'Could not attach files to the message.')
      return
    }
    await returnToComposePanel(ext)
  }

  async function returnToComposePanel(ext) {
    if (composeTabId != null) {
      await sendRuntimeMessage(ext, {
        type: 'canary-return-to-compose-panel',
        composeTabId: composeTabId,
      })
    }
    await sh().closeExtensionWindow(ext)
  }

  function wireCloseButton(ext) {
    const btn = $('btn-close')
    if (!btn) return
    btn.addEventListener('click', function () {
      void returnToComposePanel(ext)
    })
  }

  async function main() {
    const ext = sh().getGecko()
    wireCloseButton(ext)

    const p = params()
    caseId = String(p.get('caseId') || '').trim()
    const tid = p.get('composeTabId')
    composeTabId = tid != null && String(tid).trim() !== '' ? Number(tid) : null
    if (composeTabId != null && !Number.isFinite(composeTabId)) {
      composeTabId = tid
    }
    const sel = String(p.get('selected') || '').trim()
    if (sel) {
      selectedIds = sel
        .split(',')
        .map(function (s) {
          return s.trim()
        })
        .filter(Boolean)
    }

    if (!caseId) {
      showErr('No matter specified.')
      return
    }

    if (!ext) {
      showErr('Extension APIs not available.')
      return
    }

    const root = $('picker-root')
    if (root) root.innerHTML = '<div class="picker-empty">Loading files…</div>'

    try {
      const { jwt, origin } = await sh().getStoredAuth(ext)
      if (!jwt || !origin) throw new Error('Sign in via Canary first.')
      const body = await fetch(sh().apiRoot(origin) + '/cases/' + encodeURIComponent(caseId) + '/files', {
        headers: sh().authHeaders(jwt),
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
    } catch (e) {
      if (root) root.innerHTML = ''
      showErr(e.message || String(e))
      return
    }

    if (!ui()) {
      showErr('Attach UI failed to load. Reload the add-on.')
      return
    }

    $('btn-attach').addEventListener('click', function () {
      void confirmAttach()
    })

    updateFooter()
    renderList()
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', main)
  } else {
    main()
  }
})()
