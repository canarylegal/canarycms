/* global globalThis */
'use strict'
;(function () {
  var companionWindowId = null
  var filingWindowId = null
  /** @type {Record<string, number|null>} */
  var composePanelWindowByTab = {}

  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  /** Reload an extension pop-up window so popup JS re-runs for a new message/context. */
  function navigateExtensionWindowToUrl(ext, windowId, url) {
    if (!ext.tabs || typeof ext.tabs.query !== 'function' || typeof ext.tabs.update !== 'function') {
      return Promise.resolve(false)
    }
    return ext.tabs.query({ windowId: windowId }).then(function (tabs) {
      if (!tabs || !tabs.length || tabs[0].id == null) return false
      return ext.tabs.update(tabs[0].id, { url: url }).then(function () {
        return true
      })
    })
  }

  function openExtensionPopupWindow(url, trackRef, sizeOpts, windowOpts) {
    const ext = getGecko()
    if (!ext || !ext.windows || !ext.runtime.getURL) {
      return Promise.reject(new Error('windows API not available'))
    }
    const w = (sizeOpts && sizeOpts.width) || 480
    const h = (sizeOpts && sizeOpts.height) || 640
    const focusOnly = windowOpts && windowOpts.focusOnly
    const trackedId = trackRef && trackRef.id != null ? trackRef.id : null
    if (trackedId != null) {
      return ext.windows
        .get(trackedId)
        .then(function (existing) {
          if (existing && existing.id != null) {
            if (focusOnly) {
              return ext.windows
                .update(trackedId, { focused: true, drawAttention: true })
                .catch(function () {
                  return ext.windows.update(trackedId, { focused: true })
                })
                .then(function () {
                  return { ok: true, focused: true, windowId: trackedId, reloaded: false }
                })
            }
            return navigateExtensionWindowToUrl(ext, trackedId, url)
              .catch(function () {
                return false
              })
              .then(function () {
                return ext.windows
                  .update(trackedId, { focused: true, drawAttention: true })
                  .catch(function () {
                    return ext.windows.update(trackedId, { focused: true })
                  })
              })
              .then(function () {
                return { ok: true, focused: true, windowId: trackedId, reloaded: true }
              })
          }
          if (trackRef) trackRef.id = null
          return createNew()
        })
        .catch(function () {
          if (trackRef) trackRef.id = null
          return createNew()
        })
    }
    return createNew()

    function createNew() {
      const withTitle = {
        type: 'popup',
        url: url,
        width: w,
        height: h,
        titlePreface: 'Canary — ',
      }
      const minimal = { type: 'popup', url: url, width: w, height: h }
      return ext.windows.create(withTitle).catch(function () {
        return ext.windows.create(minimal)
      }).then(function (created) {
        if (trackRef && created && created.id != null) {
          trackRef.id = created.id
        }
        return { ok: true, windowId: created && created.id, focused: false }
      })
    }
  }

  /**
   * Open filing UI for a message (must be called directly — not via runtime.sendMessage from background).
   * @param {number|string} messageId
   */
  globalThis.canaryOpenFilingWindow = function (messageId) {
    const ext = getGecko()
    if (!ext || messageId == null) {
      return Promise.resolve({ ok: false, detail: 'No message or extension API.' })
    }
    const key = globalThis.canaryContextFilingMessageKey || 'canary_context_filing_message_id'
    return (async function () {
      try {
        if (ext.storage && ext.storage.session) {
          const stored =
            typeof messageId === 'number'
              ? messageId
              : parseInt(String(messageId), 10)
          await ext.storage.session.set({
            [key]: Number.isFinite(stored) ? stored : messageId,
          })
        }
        const q =
          'contextFiling=1&messageId=' + encodeURIComponent(String(messageId))
        const url = ext.runtime.getURL('popup/popup.html?' + q)
        const track = { id: filingWindowId }
        const r = await openExtensionPopupWindow(url, track)
        filingWindowId = track.id
        return r
      } catch (e) {
        console.warn('Canary filing window failed:', e)
        return { ok: false, detail: (e && e.message) || String(e) }
      }
    })()
  }

  /**
   * Open compose panel in a popup window (works without user gesture; composeAction.openPopup often does not).
   * @param {number} tabId
   */
  globalThis.canaryFocusComposePanelWindow = function (tabId) {
    const ext = getGecko()
    if (!ext || tabId == null) {
      return Promise.resolve({ ok: false, detail: 'No compose tab or extension API.' })
    }
    const key = String(tabId)
    const windowId = composePanelWindowByTab[key]
    if (windowId == null) {
      return Promise.resolve({ ok: false, detail: 'No compose panel window for tab.' })
    }
    return ext.windows
      .get(windowId)
      .then(function (existing) {
        if (!existing || existing.id == null) {
          composePanelWindowByTab[key] = null
          return { ok: false, detail: 'Compose panel window was closed.' }
        }
        return ext.windows
          .update(windowId, { focused: true, drawAttention: true })
          .catch(function () {
            return ext.windows.update(windowId, { focused: true })
          })
          .then(function () {
            return { ok: true, focused: true, windowId: windowId, reloaded: false }
          })
      })
      .catch(function () {
        composePanelWindowByTab[key] = null
        return { ok: false, detail: 'Could not focus compose panel.' }
      })
  }

  globalThis.canaryOpenComposePanelWindow = function (tabId, options) {
    const ext = getGecko()
    if (!ext || tabId == null) {
      return Promise.resolve({ ok: false, detail: 'No compose tab or extension API.' })
    }
    const force = options && options.force
    const focusOnly = options && options.focusOnly
    const key = String(tabId)
    return (async function () {
      try {
        if (force && globalThis.canaryClearComposeAutoOpened) {
          globalThis.canaryClearComposeAutoOpened(tabId)
        }
        if (globalThis.canaryComposeStore && typeof globalThis.canaryComposeStore.setActiveComposeTab === 'function') {
          await globalThis.canaryComposeStore.setActiveComposeTab(ext, tabId)
        }
        if (globalThis.canaryShared && typeof globalThis.canaryShared.setComposePanelTabId === 'function') {
          await globalThis.canaryShared.setComposePanelTabId(ext, tabId)
        }
        const q =
          'composeTabId=' +
          encodeURIComponent(String(tabId)) +
          '&autoWindow=1'
        const url = ext.runtime.getURL('compose-panel/panel.html?' + q)
        const track = { id: composePanelWindowByTab[key] != null ? composePanelWindowByTab[key] : null }
        const r = await openExtensionPopupWindow(url, track, undefined, { focusOnly: focusOnly })
        composePanelWindowByTab[key] = track.id
        return r
      } catch (e) {
        console.warn('Canary compose panel window failed:', e)
        return { ok: false, detail: (e && e.message) || String(e) }
      }
    })()
  }

  var attachPickerWindowId = null

  /**
   * @param {string} caseId
   * @param {number} composeTabId
   * @param {string[]} selectedIds
   */
  globalThis.canaryOpenAttachPickerWindow = function (caseId, composeTabId, selectedIds) {
    const ext = getGecko()
    if (!ext || !caseId || composeTabId == null) {
      return Promise.resolve({ ok: false, detail: 'Matter and compose tab required.' })
    }
    return (async function () {
      try {
        const ids = (selectedIds || []).map(String).join(',')
        const q =
          'caseId=' +
          encodeURIComponent(String(caseId)) +
          '&composeTabId=' +
          encodeURIComponent(String(composeTabId)) +
          '&selected=' +
          encodeURIComponent(ids)
        const url = ext.runtime.getURL('compose-attach-picker/attach-picker.html?' + q)
        const track = { id: attachPickerWindowId }
        const r = await openExtensionPopupWindow(url, track, { width: 520, height: 520 })
        attachPickerWindowId = track.id
        return r
      } catch (e) {
        return { ok: false, detail: (e && e.message) || String(e) }
      }
    })()
  }

  globalThis.canaryOpenCompanionWindow = function () {
    const ext = getGecko()
    if (!ext) {
      return Promise.resolve({ ok: false, detail: 'Extension API not available.' })
    }
    return (async function () {
      try {
        const url = ext.runtime.getURL('popup/popup.html?companion=1')
        const track = { id: companionWindowId }
        const r = await openExtensionPopupWindow(url, track)
        companionWindowId = track.id
        return r
      } catch (e) {
        return { ok: false, detail: (e && e.message) || String(e) }
      }
    })()
  }

  const ext = getGecko()
  if (ext && ext.windows && ext.windows.onRemoved) {
    ext.windows.onRemoved.addListener(function (windowId) {
      if (windowId === companionWindowId) companionWindowId = null
      if (windowId === filingWindowId) filingWindowId = null
      for (const k of Object.keys(composePanelWindowByTab)) {
        if (composePanelWindowByTab[k] === windowId) {
          composePanelWindowByTab[k] = null
          /* Keep openedForTab until the compose tab closes — avoids re-auto-open when editing To after closing the panel. */
        }
      }
      if (windowId === attachPickerWindowId) attachPickerWindowId = null
    })
  }
})()
