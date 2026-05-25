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

  function collectAllFolderPaths(files) {
    const set = new Set()
    for (const f of files || []) {
      const fp = (f.folder_path ?? '').trim()
      if (!fp) continue
      const parts = fp.split('/').filter(Boolean)
      let cur = ''
      for (const p of parts) {
        cur = cur ? cur + '/' + p : p
        set.add(cur)
      }
    }
    return Array.from(set).sort(function (a, b) {
      return a.localeCompare(b)
    })
  }

  function matterFilesNonSystem(files) {
    return (files || []).filter(function (f) {
      return f.category !== 'system'
    })
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

  function isAttachableFile(f) {
    const mime = (f.mime_type || '').toLowerCase()
    const name = (f.original_filename || '').toLowerCase()
    if (mime.indexOf('text/plain') === 0 || name.endsWith('.txt')) return false
    return true
  }

  /** Flat list when the matter has no files at folder root (common for e-mail-only matters). */
  function allAttachableFiles(files) {
    return matterFilesNonSystem(files)
      .filter(function (f) {
        return isAttachableFile(f)
      })
      .sort(function (a, b) {
        const fa = String(a.folder_path || '')
        const fb = String(b.folder_path || '')
        if (fa !== fb) return fa.localeCompare(fb)
        return String(a.original_filename || '').localeCompare(String(b.original_filename || ''))
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
    const selectedIds = opts.selectedIds || []
    const browseFolder = opts.browseFolder || ''
    root.innerHTML = ''

    const crumbs = document.createElement('div')
    crumbs.className = 'attach-crumbs muted'
    const home = document.createElement('button')
    home.type = 'button'
    home.className = 'attach-crumb'
    home.textContent = 'Home'
    home.onclick = function () {
      opts.onBrowseFolder('')
    }
    crumbs.appendChild(home)
    const parts = splitFolderPath(browseFolder)
    let pathAcc = ''
    for (let i = 0; i < parts.length; i++) {
      const sep = document.createElement('span')
      sep.className = 'attach-crumb-sep'
      sep.textContent = ' / '
      crumbs.appendChild(sep)
      pathAcc = pathAcc ? pathAcc + '/' + parts[i] : parts[i]
      const segPath = pathAcc
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'attach-crumb'
      btn.textContent = decodeFolderSegment(parts[i])
      btn.onclick = function () {
        opts.onBrowseFolder(segPath)
      }
      crumbs.appendChild(btn)
    }
    root.appendChild(crumbs)

    const list = document.createElement('div')
    list.className = 'attach-picker-list'

    const folders = childFolders(files, browseFolder)
    for (const folderName of folders) {
      const next = browseFolder ? browseFolder + '/' + folderName : folderName
      const row = document.createElement('button')
      row.type = 'button'
      row.className = 'attach-picker-row attach-picker-row--folder'
      const spacer = document.createElement('span')
      spacer.className = 'attach-picker-check-spacer'
      spacer.setAttribute('aria-hidden', 'true')
      row.appendChild(spacer)
      const label = document.createElement('span')
      label.textContent = decodeFolderSegment(folderName)
      row.appendChild(label)
      row.onclick = function () {
        opts.onBrowseFolder(next)
      }
      list.appendChild(row)
    }

    const docs = filesInBrowseFolder(files, browseFolder)
    if (!folders.length && !docs.length) {
      const empty = document.createElement('div')
      empty.className = 'attach-picker-empty muted'
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
        let next = selectedIds.slice()
        if (cb.checked) {
          if (next.length >= MAX_ATTACH) {
            cb.checked = false
            if (opts.onStatus) opts.onStatus('At most ' + MAX_ATTACH + ' attachments.', true)
            return
          }
          if (next.indexOf(id) < 0) next.push(id)
        } else {
          next = next.filter(function (x) {
            return x !== id
          })
        }
        opts.onSelectionChange(next)
        if (opts.onStatus) opts.onStatus(next.length + ' selected.', false)
      }
      row.appendChild(cb)
      const span = document.createElement('span')
      span.textContent = f.original_filename || id
      row.appendChild(span)
      list.appendChild(row)
    }
    root.appendChild(list)
  }

  globalThis.canaryComposeAttachUi = {
    MAX_ATTACH,
    collectAllFolderPaths,
    childFolders,
    filesInBrowseFolder,
    allAttachableFiles,
    matterFilesNonSystem,
    renderAttachPicker,
    decodeFolderSegment,
  }
})()
