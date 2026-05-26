/* global Office */
'use strict'
;(function () {
  const LS_KEY = 'canary_outlook_addin_jwt'
  const LS_API_ORIGIN_KEY = 'canary_outlook_addin_api_origin'
  const RS_KEY = 'canary_jwt'
  const RS_API_ORIGIN_KEY = 'canary_api_origin'

  function pageOrigin() {
    try {
      return new URL(window.location.href).origin
    } catch (_) {
      return ''
    }
  }

  function apiRoot() {
    return pageOrigin() + '/api'
  }

  function getToken() {
    try {
      const fromLs = localStorage.getItem(LS_KEY)
      if (fromLs) return String(fromLs)
    } catch (_) {}
    try {
      return Office.context.roamingSettings.get(RS_KEY) || ''
    } catch (_) {
      return ''
    }
  }

  function persistTokenAsync(token) {
    const v = token || ''
    try {
      if (v) {
        localStorage.setItem(LS_KEY, v)
        localStorage.setItem(LS_API_ORIGIN_KEY, pageOrigin())
      } else {
        localStorage.removeItem(LS_KEY)
        localStorage.removeItem(LS_API_ORIGIN_KEY)
      }
    } catch (e) {
      return Promise.reject(e)
    }
    return new Promise(function (resolve, reject) {
      try {
        Office.context.roamingSettings.set(RS_KEY, v)
        try {
          Office.context.roamingSettings.set(RS_API_ORIGIN_KEY, v ? pageOrigin() : '')
        } catch (_) {}
        Office.context.roamingSettings.saveAsync(function (r) {
          if (r.status === Office.AsyncResultStatus.Succeeded) {
            resolve()
            return
          }
          if (v) resolve()
          else reject(new Error(r.error ? r.error.message : 'Could not clear sign-in.'))
        })
      } catch (e) {
        if (v) resolve()
        else reject(e)
      }
    })
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

  function matterLabel(c) {
    const num = c.case_number != null ? String(c.case_number) : ''
    const client = c.client_name ? String(c.client_name) : ''
    const title = c.matter_description ? String(c.matter_description) : ''
    const primary = [num, client].filter(Boolean).join(' — ') || String(c.id)
    return title ? primary + ' — ' + title : primary
  }

  function filterCases(allCases, query) {
    const q = String(query || '')
      .trim()
      .toLowerCase()
    if (!q) return []
    return (allCases || []).filter(function (c) {
      return matterLabel(c).toLowerCase().includes(q)
    })
  }

  function collectFolderPaths(files) {
    const set = new Set()
    for (const f of files || []) {
      const fp = String(f.folder_path || '').trim()
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

  function isAttachableFile(f) {
    const mime = String(f.mime_type || '').toLowerCase()
    const name = String(f.original_filename || '').toLowerCase()
    if (mime.indexOf('text/plain') === 0 || name.endsWith('.txt')) return false
    if (f.category === 'system') return false
    return true
  }

  function attachableFiles(files) {
    return (files || [])
      .filter(isAttachableFile)
      .sort(function (a, b) {
        const fa = String(a.folder_path || '')
        const fb = String(b.folder_path || '')
        if (fa !== fb) return fa.localeCompare(fb)
        return String(a.original_filename || '').localeCompare(String(b.original_filename || ''))
      })
  }

  /** Read mode: subject is a string. Compose / send: use ``subject.getAsync``. */
  function getSubjectAsync(item) {
    return new Promise(function (resolve) {
      if (!item || !item.subject) {
        resolve('')
        return
      }
      try {
        if (typeof item.subject === 'string') {
          resolve(String(item.subject).trim())
          return
        }
        if (typeof item.subject.getAsync === 'function') {
          item.subject.getAsync(function (r) {
            if (r.status === Office.AsyncResultStatus.Succeeded) {
              resolve(String(r.value || '').trim())
              return
            }
            resolve('')
          })
          return
        }
      } catch (_) {}
      resolve('')
    })
  }

  function safeInternetMessageId(item) {
    try {
      const v = item && item.internetMessageId
      if (typeof v === 'string') {
        const s = v.trim()
        if (s && s.indexOf('[object') < 0) return s
      }
    } catch (_) {}
    return ''
  }

  function randomMessageId() {
    const id =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = (Math.random() * 16) | 0
            const v = c === 'x' ? r : (r & 0x3) | 0x8
            return v.toString(16)
          })
    return '<' + id + '@canary-outlook-addin>'
  }

  function wrapMessageId(id) {
    const s = String(id || '').trim()
    if (!s || s.indexOf('[object') >= 0) return randomMessageId()
    if (s.charAt(0) === '<') return s
    return '<' + s + '>'
  }

  globalThis.canaryOutlookShared = {
    LS_KEY: LS_KEY,
    pageOrigin: pageOrigin,
    apiRoot: apiRoot,
    getToken: getToken,
    persistTokenAsync: persistTokenAsync,
    authHeaders: authHeaders,
    jsonAuthHeaders: jsonAuthHeaders,
    matterLabel: matterLabel,
    filterCases: filterCases,
    collectFolderPaths: collectFolderPaths,
    attachableFiles: attachableFiles,
    getSubjectAsync: getSubjectAsync,
    safeInternetMessageId: safeInternetMessageId,
    wrapMessageId: wrapMessageId,
  }
})()
