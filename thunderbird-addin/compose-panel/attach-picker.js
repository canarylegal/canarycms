/* global messenger, browser */
'use strict'
;(function () {
  const sh = () => globalThis.canaryShared
  const cs = () => globalThis.canaryComposeStore
  const attachUi = () => globalThis.canaryComposeAttachUi

  let composeTabId = null
  let caseId = null
  let files = []
  let selectedIds = []
  let browseFolder = ''

  function $(id) {
    return document.getElementById(id)
  }

  function out(text, isErr) {
    const el = $('out')
    if (!el) return
    el.className = isErr ? 'err' : text ? 'ok' : ''
    el.textContent = text || ''
  }

  function parseQuery() {
    try {
      const p = new URLSearchParams(globalThis.location.search || '')
      const tid = p.get('composeTabId')
      const cid = p.get('caseId')
      composeTabId = tid != null && tid !== '' ? tid : null
      caseId = cid || null
    } catch (_) {
      composeTabId = null
      caseId = null
    }
  }

  function render() {
    const ui = attachUi()
    const root = $('attach-picker-root')
    if (!ui || !root) return
    ui.renderAttachPicker(root, {
      files: files,
      selectedIds: selectedIds,
      browseFolder: browseFolder,
      onBrowseFolder: function (path) {
        browseFolder = path
        render()
      },
      onSelectionChange: function (ids) {
        selectedIds = ids
        out(selectedIds.length + ' selected.', false)
      },
      onStatus: out,
    })
  }

  async function main() {
    parseQuery()
    const ext = sh().getGecko()
    const closeBtn = $('btn-close')
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        globalThis.close()
      })
    }
    if (!ext || !caseId || composeTabId == null) {
      out('Missing matter or compose tab.', true)
      return
    }
    try {
      const { jwt, origin } = await sh().getStoredAuth(ext)
      files = await fetch(sh().apiRoot(origin) + '/cases/' + encodeURIComponent(caseId) + '/files', {
        headers: sh().authHeaders(jwt),
      }).then(async function (res) {
        const body = await res.json().catch(function () {
          return null
        })
        if (!res.ok) throw new Error('Could not load files.')
        return body
      })
      const st = await cs().getTabState(ext, composeTabId)
      selectedIds = (st && st.attachmentFileIds) || []
      const line = $('matter-line')
      if (line) line.textContent = 'Matter: ' + caseId
      render()
      out(selectedIds.length + ' selected.', false)
    } catch (e) {
      out(e.message || String(e), true)
    }

    $('btn-done').addEventListener('click', function () {
      void (async function () {
        try {
          const st = await cs().getTabState(ext, composeTabId)
          const next = Object.assign({}, cs().blankState(), st || {}, {
            caseId: (st && st.caseId) || caseId,
            attachmentFileIds: selectedIds,
          })
          await cs().setTabState(ext, composeTabId, next)
          globalThis.close()
        } catch (e) {
          out(e.message || String(e), true)
        }
      })()
    })
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', main)
  } else {
    main()
  }
})()
