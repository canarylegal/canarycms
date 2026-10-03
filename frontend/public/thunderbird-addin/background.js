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
    return false
  })
})()
