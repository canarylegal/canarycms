/* global globalThis */
'use strict'
;(function () {
  const TAB_STATE_KEY = 'canary_compose_tab_state'
  const ACTIVE_TAB_KEY = 'canary_compose_active_tab_id'

  function blankState() {
    return {
      caseId: null,
      folder: '',
      parentFileId: null,
      precedentId: null,
      caseContactId: null,
      globalContactId: null,
      mergeAllClients: false,
      attachmentFileIds: [],
      /** User chose “None — do not file on send” for this compose tab. */
      userOverridden: false,
      /** Set when matter was inferred from reply/forward to a filed message. */
      prefilledFromReply: false,
      /** Set when matter came from pending-send (e.g. user opened the .eml from Canary). */
      prefilledFromPending: false,
      /** Reply prefill applied To/subject/body via compose-bundle without opening the panel. */
      composeAutoApplied: false,
      prefilledCaseNumber: '',
      prefilledClientName: '',
      prefilledMatterTitle: '',
      prefillStatus: '',
    }
  }

  async function getAllStates(ext) {
    const st = await ext.storage.local.get(TAB_STATE_KEY)
    const raw = (st && st[TAB_STATE_KEY]) || {}
    return typeof raw === 'object' && raw !== null ? raw : {}
  }

  async function getTabState(ext, tabId) {
    if (tabId == null) return blankState()
    const all = await getAllStates(ext)
    const key = String(tabId)
    const cur = all[key]
    return Object.assign(blankState(), cur || {})
  }

  async function setTabState(ext, tabId, patch) {
    if (tabId == null) return blankState()
    const all = await getAllStates(ext)
    const key = String(tabId)
    const next = Object.assign(blankState(), all[key] || {}, patch || {})
    all[key] = next
    await ext.storage.local.set({ [TAB_STATE_KEY]: all })
    return next
  }

  async function clearTabState(ext, tabId) {
    if (tabId == null) return
    const all = await getAllStates(ext)
    delete all[String(tabId)]
    await ext.storage.local.set({ [TAB_STATE_KEY]: all })
  }

  async function setActiveComposeTab(ext, tabId) {
    if (tabId == null) {
      await ext.storage.local.remove(ACTIVE_TAB_KEY)
      return
    }
    await ext.storage.local.set({ [ACTIVE_TAB_KEY]: tabId })
  }

  async function getActiveComposeTab(ext) {
    const st = await ext.storage.local.get(ACTIVE_TAB_KEY)
    const id = st && st[ACTIVE_TAB_KEY]
    return id != null ? id : null
  }

  function registerComposeTabTracking(ext) {
    if (!ext.compose || !ext.compose.onComposeStateChanged) return
    ext.compose.onComposeStateChanged.addListener(function (tab) {
      if (tab && tab.id != null) {
        void setActiveComposeTab(ext, tab.id)
      }
    })
  }

  globalThis.canaryComposeStore = {
    blankState,
    getTabState,
    setTabState,
    clearTabState,
    setActiveComposeTab,
    getActiveComposeTab,
    registerComposeTabTracking,
  }
})()
