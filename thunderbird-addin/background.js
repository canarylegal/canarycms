/* global messenger, browser, globalThis */
/**
 * Runtime messages from popups (not from other background scripts — use canary-windows.js directly).
 */
;(function () {
  'use strict'

  var ext = typeof messenger !== 'undefined' ? messenger : typeof browser !== 'undefined' ? browser : null
  if (!ext || !ext.runtime || !ext.runtime.onMessage) {
    return
  }

  function handleApplyFiledTag(message, sendResponse) {
    var run =
      globalThis && typeof globalThis.canaryRunApplyFiledTag === 'function'
        ? globalThis.canaryRunApplyFiledTag
        : null
    if (!run) {
      sendResponse({ ok: false, detail: 'canaryRunApplyFiledTag missing' })
      return
    }
    void (async function () {
      try {
        const r = await run(message.messageId)
        sendResponse(r)
      } catch (e) {
        sendResponse({ ok: false, detail: (e && e.message) || String(e) })
      }
    })()
  }

  ext.runtime.onMessage.addListener(function (message, _sender, sendResponse) {
    if (message && message.type === 'canary-handoff-auth-status') {
      void (async function () {
        try {
          const sh = globalThis.canaryShared
          const auth = sh && typeof sh.getStoredAuth === 'function' ? await sh.getStoredAuth(ext) : null
          sendResponse({
            signedIn: !!(auth && auth.jwt && auth.origin),
            origin: (auth && auth.origin) || '',
          })
        } catch (_) {
          sendResponse({ signedIn: false, origin: '' })
        }
      })()
      return true
    }
    if (message && message.type === 'canary-apply-filed-tag') {
      handleApplyFiledTag(message, sendResponse)
      return true
    }
    if (message && message.type === 'canary-open-companion') {
      void (async function () {
        try {
          const open = globalThis.canaryOpenCompanionWindow
          const r = open ? await open() : { ok: false, detail: 'canaryOpenCompanionWindow missing' }
          sendResponse(r)
        } catch (e) {
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        }
      })()
      return true
    }
    if (message && message.type === 'canary-record-filed-message') {
      void (async function () {
        try {
          const rec = globalThis.canaryShared && globalThis.canaryShared.recordFiledTbMessage
          if (!rec) {
            sendResponse({ ok: false, detail: 'recordFiledTbMessage missing' })
            return
          }
          await rec(
            ext,
            message.tbMessageId,
            message.caseId,
            message.fileId,
            message.internetMessageId,
          )
          const sync = globalThis.canaryShared.syncPendingSend
          if (sync && message.caseId) {
            const auth = await globalThis.canaryShared.getStoredAuth(ext)
            if (auth.jwt && auth.origin) {
              await sync(auth.jwt, auth.origin, String(message.caseId), message.fileId || null)
            }
          }
          sendResponse({ ok: true })
        } catch (e) {
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        }
      })()
      return true
    }
    if (message && message.type === 'canary-open-attach-picker') {
      // Single-flight across duplicate listeners / double clicks (do not clear until open settles).
      if (globalThis.__canaryOpenAttachPickerPromise) {
        void globalThis.__canaryOpenAttachPickerPromise.then(function (r) {
          sendResponse(r || { ok: true, deduped: true })
        })
        return true
      }
      globalThis.__canaryOpenAttachPickerPromise = (async function () {
        try {
          const open = globalThis.canaryOpenAttachPickerWindow
          return open
            ? await open(message.caseId, message.composeTabId, message.selectedIds || [])
            : { ok: false, detail: 'canaryOpenAttachPickerWindow missing' }
        } catch (e) {
          return { ok: false, detail: (e && e.message) || String(e) }
        } finally {
          const held = globalThis.__canaryOpenAttachPickerPromise
          setTimeout(function () {
            if (globalThis.__canaryOpenAttachPickerPromise === held) {
              globalThis.__canaryOpenAttachPickerPromise = null
            }
          }, 1500)
        }
      })()
      void globalThis.__canaryOpenAttachPickerPromise.then(function (r) {
        sendResponse(r)
      })
      return true
    }
    if (message && message.type === 'canary-open-compose-panel') {
      void (async function () {
        try {
          const tabId = message.composeTabId
          const fromToolbar = globalThis.canaryOpenComposePanelFromToolbar
          const openWindow = globalThis.canaryOpenComposePanelWindow
          let r
          if (typeof fromToolbar === 'function') {
            r = await fromToolbar(ext, { id: tabId })
          } else if (typeof openWindow === 'function') {
            r = await openWindow(tabId, { force: true })
          } else {
            r = { ok: false, detail: 'Compose panel opener missing' }
          }
          sendResponse(r)
        } catch (e) {
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        }
      })()
      return true
    }
    if (message && message.type === 'canary-apply-compose-attachments') {
      void (async function () {
        const tabId = message.composeTabId
        const caseId = message.caseId
        const lockKey = String(tabId) + ':' + String(caseId)
        if (globalThis.__canaryAttachInflight && globalThis.__canaryAttachInflight[lockKey]) {
          sendResponse({ ok: false, detail: 'Attach already in progress.' })
          return
        }
        if (!globalThis.__canaryAttachInflight) globalThis.__canaryAttachInflight = {}
        globalThis.__canaryAttachInflight[lockKey] = true
        try {
          const cs = globalThis.canaryComposeStore
          const sh = globalThis.canaryShared
          const applyAtt = globalThis.canaryApplyComposeAttachments
          if (!cs || !sh || !applyAtt || tabId == null || !caseId) {
            sendResponse({ ok: false, detail: 'Attach apply not available.' })
            return
          }
          const { jwt, origin } = await sh.getStoredAuth(ext)
          if (!jwt || !origin) {
            sendResponse({ ok: false, detail: 'Sign in via Canary first.' })
            return
          }
          const st = await cs.getTabState(ext, tabId)
          const ids = (st && st.attachmentFileIds) || []
          if (!ids.length) {
            sendResponse({ ok: false, detail: 'No files selected.' })
            return
          }
          const body = {
            folder: st.folder || '',
            precedent_id: st.precedentId || null,
            case_contact_id: st.caseContactId || null,
            global_contact_id: null,
            precedent_merge_all_clients: !!st.mergeAllClients,
            attachment_file_ids: ids,
          }
          const res = await fetch(
            sh.apiRoot(origin) + '/mail-plugin/cases/' + encodeURIComponent(String(caseId)) + '/compose-bundle',
            { method: 'POST', headers: sh.jsonAuthHeaders(jwt), body: JSON.stringify(body) },
          )
          const bundle = await res.json().catch(function () {
            return null
          })
          if (!res.ok) {
            const detail = bundle && bundle.detail
            sendResponse({
              ok: false,
              detail: typeof detail === 'string' ? detail : 'Compose bundle failed',
            })
            return
          }
          await applyAtt(ext, tabId, bundle)
          sendResponse({ ok: true })
        } catch (e) {
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        } finally {
          if (globalThis.__canaryAttachInflight) delete globalThis.__canaryAttachInflight[lockKey]
        }
      })()
      return true
    }
    if (message && message.type === 'canary-return-to-compose-panel') {
      void (async function () {
        try {
          const tabId = message.composeTabId
          const focusOnly = message.focusOnly !== false
          const focusWindow = globalThis.canaryFocusComposePanelWindow
          const openWindow = globalThis.canaryOpenComposePanelWindow
          let r
          if (typeof focusWindow === 'function') {
            r = await focusWindow(tabId)
            if (r && r.ok) {
              sendResponse(r)
              return
            }
          }
          if (focusOnly) {
            // Do not create a new panel when returning from attach/close flows.
            sendResponse({ ok: true, focused: false, skippedOpen: true })
            return
          }
          if (typeof openWindow === 'function') {
            r = await openWindow(tabId, { focusOnly: true })
            if (r && r.ok) {
              sendResponse(r)
              return
            }
            r = await openWindow(tabId)
            sendResponse(r)
            return
          }
          sendResponse({ ok: false, detail: 'Compose panel opener missing' })
        } catch (e) {
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        }
      })()
      return true
    }
    if (message && message.type === 'canary-open-filing-window') {
      void (async function () {
        try {
          const open = globalThis.canaryOpenFilingWindow
          const r = open
            ? await open(message.messageId)
            : { ok: false, detail: 'canaryOpenFilingWindow missing' }
          sendResponse(r)
        } catch (e) {
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        }
      })()
      return true
    }
    if (message && message.type === 'canary-plugin-connect') {
      // Must run in the background script: the toolbar popup is destroyed when the user
      // switches to the browser to authorize, which previously aborted the token wait.
      void (async function () {
        try {
          const sh = globalThis.canaryShared
          if (!sh || typeof sh.runPluginConnect !== 'function') {
            sendResponse({ ok: false, detail: 'Connect helper not loaded in background.' })
            return
          }
          if (globalThis.__canaryPluginConnectPromise) {
            sendResponse({
              ok: false,
              detail:
                'A Canary sign-in is already in progress. Finish authorizing in your browser, then reopen Canary.',
            })
            return
          }
          const origin = message.origin
          const client = message.client || 'thunderbird'
          globalThis.__canaryPluginConnectPromise = sh.runPluginConnect(ext, origin, client)
          try {
            await globalThis.__canaryPluginConnectPromise
            sendResponse({ ok: true })
          } finally {
            globalThis.__canaryPluginConnectPromise = null
          }
        } catch (e) {
          globalThis.__canaryPluginConnectPromise = null
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        }
      })()
      return true
    }
    if (message && message.type === 'canary-open-eml-url') {
      void (async function () {
        let claimedFileId = null
        let reserved = false
        try {
          const url = message.url
          if (!url || typeof url !== 'string' || !/\/files\/[^/]+\/eml-open\?/i.test(url)) {
            sendResponse({ ok: false, detail: 'Unsupported open URL.' })
            return
          }
          // Short race guard vs poller only (same file_id within ~2.5s).
          try {
            const m = /\/files\/([^/]+)\/eml-open\?/i.exec(url)
            claimedFileId = m && m[1]
            if (claimedFileId && typeof globalThis.canaryMarkEmlOpened === 'function') {
              if (!globalThis.canaryMarkEmlOpened(claimedFileId)) {
                sendResponse({ ok: true, deduped: true })
                return
              }
              reserved = true
            }
          } catch (_) {
            /* ignore */
          }
          if (!ext.messageDisplay || typeof ext.messageDisplay.open !== 'function') {
            if (reserved && claimedFileId && typeof globalThis.canaryClearEmlOpened === 'function') {
              globalThis.canaryClearEmlOpened(claimedFileId)
            }
            sendResponse({ ok: false, detail: 'Thunderbird cannot open message files in this build.' })
            return
          }
          const res = await fetch(url)
          if (!res.ok) {
            if (reserved && claimedFileId && typeof globalThis.canaryClearEmlOpened === 'function') {
              globalThis.canaryClearEmlOpened(claimedFileId)
            }
            sendResponse({ ok: false, detail: 'Could not download the e-mail (' + res.status + ').' })
            return
          }
          const buf = await res.arrayBuffer()
          let name = typeof message.filename === 'string' && message.filename.trim() ? message.filename.trim() : 'message.eml'
          if (!/\.eml$/i.test(name)) name = name.replace(/\.[^.]+$/, '') + '.eml'
          const file = new File([buf], name, { type: 'message/rfc822' })
          let opened = false
          if (typeof globalThis.canaryOpenEmlFile === 'function') {
            opened = !!(await globalThis.canaryOpenEmlFile(ext, file))
          } else if (ext.messageDisplay && typeof ext.messageDisplay.open === 'function') {
            await ext.messageDisplay.open({ file: file, location: 'window' })
            opened = true
          }
          if (claimedFileId && typeof globalThis.canaryEndEmlOpen === 'function') {
            globalThis.canaryEndEmlOpen(claimedFileId, opened)
          } else if (!opened && reserved && claimedFileId && typeof globalThis.canaryClearEmlOpened === 'function') {
            globalThis.canaryClearEmlOpened(claimedFileId)
          }
          sendResponse({ ok: opened })
        } catch (e) {
          if (claimedFileId && typeof globalThis.canaryEndEmlOpen === 'function') {
            globalThis.canaryEndEmlOpen(claimedFileId, false)
          } else if (reserved && claimedFileId && typeof globalThis.canaryClearEmlOpened === 'function') {
            globalThis.canaryClearEmlOpened(claimedFileId)
          }
          sendResponse({ ok: false, detail: (e && e.message) || String(e) })
        }
      })()
      return true
    }
    return false
  })

  // Protocol handler opens open-handoff.html — poll then close that tab so it doesn't linger.
  if (ext.tabs && typeof ext.tabs.onUpdated === 'object' && ext.tabs.onUpdated.addListener) {
    const closing = Object.create(null)
    ext.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
      const u = String((tab && tab.url) || changeInfo.url || '')
      if (!/open-handoff\.html/i.test(u)) return
      if (closing[tabId]) return
      closing[tabId] = true
      if (typeof globalThis.canaryPollPendingEmlOpen === 'function') {
        void globalThis.canaryPollPendingEmlOpen()
      }
      setTimeout(function () {
        try {
          void ext.tabs.remove(tabId)
        } catch (_) {
          /* ignore */
        }
        delete closing[tabId]
      }, 500)
    })
  }
})()

