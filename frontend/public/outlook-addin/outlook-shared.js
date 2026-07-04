/* global Office */
'use strict'
;(function () {
  const LS_KEY = 'canary_outlook_addin_jwt'
  const LS_API_ORIGIN_KEY = 'canary_outlook_addin_api_origin'
  const RS_KEY = 'canary_jwt'
  const RS_API_ORIGIN_KEY = 'canary_api_origin'
  const RS_PENDING_CASE_KEY = 'canary_pending_send_case_id'
  const RS_PENDING_EXPIRES_KEY = 'canary_pending_send_expires_ms'
  const ITEM_CASE_KEY = 'canary_case_id'

  function pageOrigin() {
    try {
      return new URL(window.location.href).origin
    } catch (_) {
      return ''
    }
  }

  function storedApiOrigin() {
    try {
      const fromLs = localStorage.getItem(LS_API_ORIGIN_KEY)
      if (fromLs) return String(fromLs).trim().replace(/\/$/, '')
    } catch (_) {}
    try {
      const fromRo = Office.context.roamingSettings.get(RS_API_ORIGIN_KEY)
      if (fromRo) return String(fromRo).trim().replace(/\/$/, '')
    } catch (_) {}
    return pageOrigin()
  }

  function apiRoot() {
    const origin = storedApiOrigin()
    return origin ? origin + '/api' : ''
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

  /** OnMessageSend runs in a separate runtime — localStorage may be empty; use OfficeRuntime.storage + roaming. */
  function getTokenAsync() {
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.getItem) {
      return OfficeRuntime.storage.getItem(LS_KEY).then(function (fromRt) {
        if (fromRt) return String(fromRt)
        return getToken()
      }).catch(function () {
        return getToken()
      })
    }
    return Promise.resolve(getToken())
  }

  function mirrorAuthToEventRuntimeAsync(token) {
    if (typeof OfficeRuntime === 'undefined' || !OfficeRuntime.storage || !OfficeRuntime.storage.setItem) {
      return Promise.resolve()
    }
    const origin = storedApiOrigin()
    if (!token) {
      return Promise.all([
        OfficeRuntime.storage.removeItem(LS_KEY).catch(function () {}),
        OfficeRuntime.storage.removeItem(LS_API_ORIGIN_KEY).catch(function () {}),
      ])
    }
    return Promise.all([
      OfficeRuntime.storage.setItem(LS_KEY, String(token)),
      OfficeRuntime.storage.setItem(LS_API_ORIGIN_KEY, origin),
    ]).catch(function () {})
  }

  function readPendingSendCaseIdSync() {
    try {
      const expRaw = Office.context.roamingSettings.get(RS_PENDING_EXPIRES_KEY)
      const exp = parseInt(String(expRaw || '0'), 10)
      if (exp && Date.now() > exp) return ''
      return String(Office.context.roamingSettings.get(RS_PENDING_CASE_KEY) || '').trim()
    } catch (_) {
      return ''
    }
  }

  function readCaseIdFromItemAsync(item) {
    return new Promise(function (resolve) {
      if (!item || typeof item.loadCustomPropertiesAsync !== 'function') {
        resolve('')
        return
      }
      item.loadCustomPropertiesAsync(function (r) {
        if (r.status !== Office.AsyncResultStatus.Succeeded || !r.value) {
          resolve('')
          return
        }
        try {
          const v = r.value.get(ITEM_CASE_KEY)
          resolve(v ? String(v).trim() : '')
        } catch (_) {
          resolve('')
        }
      })
    })
  }

  function persistCaseOnItemAsync(item, caseId) {
    return new Promise(function (resolve, reject) {
      if (!item || typeof item.loadCustomPropertiesAsync !== 'function') {
        resolve(false)
        return
      }
      const v = caseId ? String(caseId).trim() : ''
      item.loadCustomPropertiesAsync(function (r) {
        if (r.status !== Office.AsyncResultStatus.Succeeded || !r.value) {
          reject(new Error(r.error ? r.error.message : 'Could not load message properties.'))
          return
        }
        const props = r.value
        try {
          if (v) props.set(ITEM_CASE_KEY, v)
          else props.remove(ITEM_CASE_KEY)
        } catch (e) {
          reject(e)
          return
        }
        props.saveAsync(function (sr) {
          if (sr.status === Office.AsyncResultStatus.Succeeded) resolve(true)
          else reject(new Error(sr.error ? sr.error.message : 'Could not save message properties.'))
        })
      })
    })
  }

  async function bindPendingMatterToComposeItem(token) {
    const item = Office.context.mailbox && Office.context.mailbox.item
    if (!item || !token) return ''
    const existing = await readCaseIdFromItemAsync(item)
    if (existing) return existing
    let caseId = ''
    try {
      const res = await fetch(apiRoot() + '/mail-plugin/pending-send', { headers: authHeaders(token) })
      const body = await res.json().catch(function () {
        return null
      })
      if (res.ok && body && body.active && body.case_id) {
        caseId = String(body.case_id)
      }
    } catch (_) {}
    if (!caseId) caseId = readPendingSendCaseIdSync()
    if (!caseId) caseId = await readPendingSendCaseIdAsync()
    if (!caseId) return ''
    await persistCaseOnItemAsync(item, caseId)
    await persistPendingSendAsync(caseId, 86400)
    await mirrorAuthToEventRuntimeAsync(token)
    return caseId
  }

  /** OnMessageSend may run before roaming settings hydrate — prefer OfficeRuntime.storage. */
  function readPendingSendCaseIdAsync() {
    const fromRoaming = readPendingSendCaseIdSync()
    if (fromRoaming) return Promise.resolve(fromRoaming)
    if (typeof OfficeRuntime === 'undefined' || !OfficeRuntime.storage || !OfficeRuntime.storage.getItem) {
      return Promise.resolve('')
    }
    return Promise.all([
      OfficeRuntime.storage.getItem(RS_PENDING_CASE_KEY).catch(function () {
        return ''
      }),
      OfficeRuntime.storage.getItem(RS_PENDING_EXPIRES_KEY).catch(function () {
        return ''
      }),
    ]).then(function (arr) {
      const id = arr[0] ? String(arr[0]).trim() : ''
      const exp = parseInt(String(arr[1] || '0'), 10)
      if (id && exp && Date.now() > exp) return ''
      return id
    })
  }

  function persistPendingSendAsync(caseId, ttlSeconds) {
    const ttl = ttlSeconds == null ? 86400 : Number(ttlSeconds)
    const exp = Date.now() + Math.max(60, ttl) * 1000
    const v = caseId ? String(caseId) : ''
    return new Promise(function (resolve, reject) {
      try {
        if (v) {
          Office.context.roamingSettings.set(RS_PENDING_CASE_KEY, v)
          Office.context.roamingSettings.set(RS_PENDING_EXPIRES_KEY, String(exp))
        } else {
          Office.context.roamingSettings.remove(RS_PENDING_CASE_KEY)
          Office.context.roamingSettings.remove(RS_PENDING_EXPIRES_KEY)
        }
        Office.context.roamingSettings.saveAsync(function (r) {
          if (r.status === Office.AsyncResultStatus.Succeeded || v) resolve()
          else reject(new Error(r.error ? r.error.message : 'Could not save pending send.'))
        })
      } catch (e) {
        if (v) resolve()
        else reject(e)
      }
    }).then(function () {
      if (typeof OfficeRuntime === 'undefined' || !OfficeRuntime.storage || !OfficeRuntime.storage.setItem) {
        return
      }
      const tasks = []
      if (v) {
        tasks.push(OfficeRuntime.storage.setItem(RS_PENDING_CASE_KEY, v).catch(function () {}))
        tasks.push(OfficeRuntime.storage.setItem(RS_PENDING_EXPIRES_KEY, String(exp)).catch(function () {}))
      } else {
        tasks.push(OfficeRuntime.storage.removeItem(RS_PENDING_CASE_KEY).catch(function () {}))
        tasks.push(OfficeRuntime.storage.removeItem(RS_PENDING_EXPIRES_KEY).catch(function () {}))
      }
      return Promise.all(tasks)
    })
  }

  async function clearPendingSendAsync(token) {
    await fetch(apiRoot() + '/mail-plugin/pending-send', {
      method: 'DELETE',
      headers: authHeaders(token),
    }).catch(function () {})
    await persistPendingSendAsync(null)
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
            void mirrorAuthToEventRuntimeAsync(v).finally(resolve)
            return
          }
          if (v) {
            void mirrorAuthToEventRuntimeAsync(v).finally(resolve)
            return
          }
          reject(new Error(r.error ? r.error.message : 'Could not clear sign-in.'))
        })
      } catch (e) {
        if (v) {
          void mirrorAuthToEventRuntimeAsync(v).finally(resolve)
          return
        }
        reject(e)
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

  function randomPluginState() {
    const bytes = new Uint8Array(24)
    crypto.getRandomValues(bytes)
    let out = ''
    for (let i = 0; i < bytes.length; i++) {
      out += String(bytes[i]).padStart(3, '0')
    }
    return out.slice(0, 32)
  }

  function getOutlookPluginAuthCallbackUrl() {
    return pageOrigin() + '/outlook-addin/auth-callback.html'
  }

  function buildPluginConnectUrl(origin, client, state, redirectUri) {
    const base = String(origin || '')
      .trim()
      .replace(/\/$/, '')
    const url = new URL(base + '/connect/mail-plugin')
    url.searchParams.set('client', client)
    url.searchParams.set('state', state)
    url.searchParams.set('redirect_uri', redirectUri)
    return url.toString()
  }

  async function exchangePluginToken(origin, client, state, code) {
    const root = String(origin || '')
      .trim()
      .replace(/\/$/, '')
    const res = await fetch(root + '/api/auth/plugin/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ client: client, state: state, code: code }),
    })
    const body = await res.json().catch(function () {
      return null
    })
    if (!res.ok) {
      const detail = body && typeof body === 'object' && body.detail
      throw new Error(typeof detail === 'string' ? detail : 'Could not complete add-in authorization.')
    }
    const token = body && body.access_token
    if (!token) throw new Error('No access token returned.')
    return String(token)
  }

  function runPluginConnect() {
    return new Promise(function (resolve, reject) {
      const origin = pageOrigin()
      if (!origin) {
        reject(new Error('Could not determine Canary site URL.'))
        return
      }
      const state = randomPluginState()
      const redirectUri = getOutlookPluginAuthCallbackUrl()
      const connectUrl = buildPluginConnectUrl(origin, 'outlook', state, redirectUri)
      if (!Office.context.ui || typeof Office.context.ui.displayDialogAsync !== 'function') {
        reject(new Error('Cannot open a sign-in window in this Outlook client.'))
        return
      }
      Office.context.ui.displayDialogAsync(
        connectUrl,
        { height: 65, width: 35, displayInIframe: false },
        function (asyncResult) {
          if (asyncResult.status !== Office.AsyncResultStatus.Succeeded) {
            const msg =
              asyncResult.error && asyncResult.error.message
                ? asyncResult.error.message
                : 'Could not open sign-in window.'
            reject(new Error(msg))
            return
          }
          const dialog = asyncResult.value
          let settled = false
          function finish(err, token) {
            if (settled) return
            settled = true
            try {
              dialog.close()
            } catch (_) {}
            if (err) reject(err)
            else resolve(token)
          }
          dialog.addEventHandler(Office.EventType.DialogMessageReceived, function (arg) {
            let payload
            try {
              payload = JSON.parse(arg.message)
            } catch (_) {
              finish(new Error('Invalid authorization response.'))
              return
            }
            if (payload.error) {
              finish(new Error(String(payload.error)))
              return
            }
            if (!payload.code || payload.state !== state) {
              finish(new Error('Authorization did not complete.'))
              return
            }
            exchangePluginToken(origin, 'outlook', state, payload.code)
              .then(function (token) {
                return persistTokenAsync(token).then(function () {
                  return token
                })
              })
              .then(function (token) {
                finish(null, token)
              })
              .catch(function (e) {
                finish(e instanceof Error ? e : new Error('Could not complete authorization.'))
              })
          })
          dialog.addEventHandler(Office.EventType.DialogEventReceived, function (arg) {
            if (arg.error === 12006) {
              finish(new Error('Sign-in window was closed.'))
            }
          })
        },
      )
    })
  }

  globalThis.canaryOutlookShared = {
    LS_KEY: LS_KEY,
    pageOrigin: pageOrigin,
    apiRoot: apiRoot,
    getToken: getToken,
    getTokenAsync: getTokenAsync,
    persistTokenAsync: persistTokenAsync,
    mirrorAuthToEventRuntimeAsync: mirrorAuthToEventRuntimeAsync,
    readPendingSendCaseIdSync: readPendingSendCaseIdSync,
    readPendingSendCaseIdAsync: readPendingSendCaseIdAsync,
    readCaseIdFromItemAsync: readCaseIdFromItemAsync,
    persistCaseOnItemAsync: persistCaseOnItemAsync,
    bindPendingMatterToComposeItem: bindPendingMatterToComposeItem,
    persistPendingSendAsync: persistPendingSendAsync,
    clearPendingSendAsync: clearPendingSendAsync,
    authHeaders: authHeaders,
    jsonAuthHeaders: jsonAuthHeaders,
    matterLabel: matterLabel,
    filterCases: filterCases,
    collectFolderPaths: collectFolderPaths,
    attachableFiles: attachableFiles,
    getSubjectAsync: getSubjectAsync,
    safeInternetMessageId: safeInternetMessageId,
    wrapMessageId: wrapMessageId,
    runPluginConnect: runPluginConnect,
    exchangePluginToken: exchangePluginToken,
    buildPluginConnectUrl: buildPluginConnectUrl,
  }
})()
