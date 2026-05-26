/* global globalThis */
'use strict'
;(function () {
  const MAX_ATTACH = 25

  function decodeFolderSegment(seg) {
    try {
      return decodeURIComponent(String(seg || ''))
    } catch (_) {
      return String(seg || '')
    }
  }

  function splitFolderPath(path) {
    return String(path || '')
      .split('/')
      .filter(Boolean)
  }

  function matterFilesNonSystem(files) {
    return (files || []).filter(function (f) {
      return f.category !== 'system'
    })
  }

  function isAttachableFile(f) {
    const mime = String(f.mime_type || '').toLowerCase()
    const name = String(f.original_filename || '').toLowerCase()
    if (mime.indexOf('text/plain') === 0 || name.endsWith('.txt')) return false
    return true
  }

  function childFolders(files, browseFolder) {
    const set = new Set()
    const basePrefix = browseFolder ? browseFolder + '/' : ''
    for (const f of matterFilesNonSystem(files)) {
      const fp = f.folder_path ?? ''
      if (fp === browseFolder) continue
      if (browseFolder && !fp.startsWith(basePrefix)) continue
      const rest = browseFolder ? fp.slice(basePrefix.length) : fp
      const first = rest.split('/').filter(Boolean)[0]
      if (first) set.add(first)
    }
    return Array.from(set).sort(function (a, b) {
      return a.localeCompare(b)
    })
  }

  function filesInBrowseFolder(files, browseFolder) {
    return matterFilesNonSystem(files)
      .filter(function (f) {
        return (f.folder_path ?? '') === browseFolder && !f.parent_file_id && isAttachableFile(f)
      })
      .sort(function (a, b) {
        return String(a.original_filename || '').localeCompare(String(b.original_filename || ''))
      })
  }

  function allAttachableFiles(files) {
    return matterFilesNonSystem(files)
      .filter(isAttachableFile)
      .sort(function (a, b) {
        const fa = String(a.folder_path || '')
        const fb = String(b.folder_path || '')
        if (fa !== fb) return fa.localeCompare(fb)
        return String(a.original_filename || '').localeCompare(String(b.original_filename || ''))
      })
  }

  /**
   * @param {HTMLElement} root
   * @param {{
   *   files: object[],
   *   selectedIds: string[],
   *   browseFolder: string,
   *   onBrowseFolder: (path: string) => void,
   *   onSelectionChange: (ids: string[]) => void,
   *   onStatus?: (text: string, isErr?: boolean) => void,
   * }} opts
   */
  function renderAttachPicker(root, opts) {
    if (!root) return
    const files = opts.files || []
    let selectedIds = opts.selectedIds || []
    const browseFolder = opts.browseFolder || ''
    root.innerHTML = ''

    const crumbs = document.createElement('div')
    crumbs.className = 'attach-crumbs'
    const home = document.createElement('button')
    home.type = 'button'
    home.className = 'attach-crumb'
    home.textContent = 'All files'
    home.onclick = function () {
      opts.onBrowseFolder('')
    }
    crumbs.appendChild(home)
    let pathAcc = ''
    for (const part of splitFolderPath(browseFolder)) {
      const sep = document.createElement('span')
      sep.className = 'attach-crumb-sep'
      sep.textContent = ' / '
      crumbs.appendChild(sep)
      pathAcc = pathAcc ? pathAcc + '/' + part : part
      const segPath = pathAcc
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'attach-crumb'
      btn.textContent = decodeFolderSegment(part)
      btn.onclick = function () {
        opts.onBrowseFolder(segPath)
      }
      crumbs.appendChild(btn)
    }
    root.appendChild(crumbs)

    const list = document.createElement('div')
    list.className = 'attach-picker-list'

    const folders = childFolders(files, browseFolder)
    let docs = filesInBrowseFolder(files, browseFolder)
    if (!folders.length && !docs.length && browseFolder === '') {
      docs = allAttachableFiles(files)
      if (docs.length) {
        const hint = document.createElement('div')
        hint.className = 'picker-empty'
        hint.textContent = 'Open a folder above, or pick a file below:'
        list.appendChild(hint)
      }
    }

    for (const folderName of folders) {
      const next = browseFolder ? browseFolder + '/' + folderName : folderName
      const row = document.createElement('button')
      row.type = 'button'
      row.className = 'attach-picker-row attach-picker-row--folder'
      row.textContent = '📁 ' + decodeFolderSegment(folderName)
      row.onclick = function () {
        opts.onBrowseFolder(next)
      }
      list.appendChild(row)
    }

    if (!folders.length && !docs.length) {
      const empty = document.createElement('div')
      empty.className = 'picker-empty'
      empty.textContent = 'No attachable files in this folder.'
      list.appendChild(empty)
    }

    for (const f of docs) {
      const id = String(f.id)
      const row = document.createElement('label')
      row.className = 'attach-picker-row attach-picker-row--file'
      const cb = document.createElement('input')
      cb.type = 'checkbox'
      cb.checked = selectedIds.indexOf(id) >= 0
      cb.onchange = function () {
        if (cb.checked) {
          if (selectedIds.length >= MAX_ATTACH) {
            cb.checked = false
            if (opts.onStatus) opts.onStatus('At most ' + MAX_ATTACH + ' attachments.', true)
            return
          }
          if (selectedIds.indexOf(id) < 0) selectedIds = selectedIds.concat([id])
        } else {
          selectedIds = selectedIds.filter(function (x) {
            return x !== id
          })
        }
        opts.onSelectionChange(selectedIds.slice())
        if (opts.onStatus) opts.onStatus(selectedIds.length + ' selected.', false)
      }
      const span = document.createElement('span')
      span.textContent = f.original_filename || id
      row.appendChild(cb)
      row.appendChild(span)
      list.appendChild(row)
    }
    root.appendChild(list)
  }

  globalThis.canaryOutlookAttachUi = {
    MAX_ATTACH: MAX_ATTACH,
    renderAttachPicker: renderAttachPicker,
  }
})()
