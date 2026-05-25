/* global messenger, browser, globalThis */
/**
 * List/create “Canary” tags and set them on a message. Runs in the **background** page
 * (see manifest) because `messenger.messages.tags` is not reliably available from the
 * `browser_action` popup — there `messages.tags` is often missing, so `create`/`list` never run.
 */
'use strict'
;(function () {
  const CANARY_TAG_KEY = 'canaryfiled'
  const TAG_NAME = 'Canary'
  const TAG_COLOR = '#1D4ED8'

  function getGecko() {
    return typeof globalThis.messenger !== 'undefined' ? globalThis.messenger : globalThis.browser
  }

  function tagRowDisplayName(row) {
    if (!row) return ''
    if (row.tag != null) return String(row.tag).trim()
    if (row.label != null) return String(row.label).trim()
    return ''
  }

  function getMessageTagsApi() {
    const g = getGecko()
    if (g && g.messages && g.messages.tags && g.messages.tags.list && g.messages.tags.create) {
      return g.messages.tags
    }
    return null
  }

  function findExistingCanaryKey(list) {
    for (const row of list || []) {
      if (row && row.key && tagRowDisplayName(row).toLowerCase() === 'canary') {
        return row.key
      }
    }
    for (const row of list || []) {
      if (row && row.key) {
        const k = String(row.key).toLowerCase()
        if (k === CANARY_TAG_KEY || k === 'canary') {
          return row.key
        }
      }
    }
    return null
  }

  function pickCreatedKey(created) {
    if (created == null) {
      return null
    }
    if (typeof created === 'string' && created.trim() !== '') {
      return created.trim()
    }
    if (typeof created === 'object' && created !== null && typeof created.key === 'string' && created.key) {
      return String(created.key)
    }
    return null
  }

  function normalizeMessageId(id) {
    if (id == null) {
      return id
    }
    if (typeof id === 'number' && !Number.isNaN(id)) {
      return id
    }
    const n = parseInt(String(id), 10)
    if (!Number.isNaN(n) && String(n) === String(id)) {
      return n
    }
    return id
  }

  async function resolveOrCreateCanaryTagKey() {
    const g = getGecko()
    const m = g && g.messages
    if (!m) {
      return { key: null, err: 'messenger.messages is not available' }
    }
    const tapi = getMessageTagsApi()
    if (tapi) {
      var list
      try {
        list = await tapi.list()
      } catch (e) {
        return { key: null, err: (e && e.message) || String(e) }
      }
      const existing = findExistingCanaryKey(list)
      if (existing) {
        return { key: existing, err: null }
      }
      var lastErr = ''
      const createTries = [
        function () {
          return tapi.create(void 0, TAG_NAME, TAG_COLOR)
        },
        function () {
          return tapi.create('canary', TAG_NAME, TAG_COLOR)
        },
        function () {
          return tapi.create(CANARY_TAG_KEY, TAG_NAME, TAG_COLOR)
        },
        function () {
          return tapi.create(TAG_NAME, TAG_COLOR)
        },
      ]
      for (var j = 0; j < createTries.length; j++) {
        var created
        try {
          created = await createTries[j]()
        } catch (e) {
          lastErr = (e && e.message) || String(e)
        }
        var fromCreate = pickCreatedKey(created)
        if (fromCreate) {
          return { key: fromCreate, err: null }
        }
        var list2
        try {
          list2 = await tapi.list()
        } catch (e2) {
          lastErr = (e2 && e2.message) || String(e2)
        }
        var f = list2 && findExistingCanaryKey(list2)
        if (f) {
          return { key: f, err: null }
        }
      }
      return {
        key: null,
        err:
          lastErr ||
          'tags.list/create failed (message tags are implemented in the background in this add-on; reload the add-on and try again).',
      }
    }
    if (typeof m.createTag === 'function') {
      try {
        await m.createTag(CANARY_TAG_KEY, TAG_NAME, TAG_COLOR)
        return { key: CANARY_TAG_KEY, err: null }
      } catch (e) {
        var s = (e && e.message) || String(e)
        if (!/exists|in use|already|duplicate|same|used|already exists/i.test(s)) {
          return { key: null, err: s }
        }
        return { key: CANARY_TAG_KEY, err: null }
      }
    }
    return {
      key: null,
      err: 'messages.tags is not available. Ensure Thunderbird 128+ and the add-on background is loaded.',
    }
  }

  /**
   * @param {number|undefined} messageId
   * @returns {Promise<{ ok: boolean, detail: string }>}
   */
  async function canaryRunApplyFiledTag(messageId) {
    const id0 = normalizeMessageId(messageId)
    const g = getGecko()
    const m = g && g.messages
    if (!m || typeof m.update !== 'function') {
      return { ok: false, detail: 'messages.update is not available' }
    }
    const r0 = await resolveOrCreateCanaryTagKey()
    const key = r0 && r0.key
    const tagErr = r0 && r0.err
    if (!key) {
      try {
        await m.update(id0, { flagged: true })
        return {
          ok: true,
          detail: tagErr
            ? 'Could not create tag: ' + tagErr + ' Starred the list row instead.'
            : 'No tag key; starred the list row instead.',
        }
      } catch (e) {
        return {
          ok: false,
          detail: (tagErr ? tagErr + ' ' : '') + ((e && e.message) || String(e)),
        }
      }
    }
    var list = []
    try {
      const msg = await m.get(id0)
      list = msg && Array.isArray(msg.tags) ? msg.tags.slice() : []
    } catch (e) {
      list = []
    }
    if (list.indexOf(key) === -1) {
      list = list.slice()
      list.push(key)
    }
    try {
      await m.update(id0, { tags: list })
    } catch (e1) {
      var w1 = (e1 && e1.message) || String(e1)
      try {
        await m.update(id0, { tags: [key] })
      } catch (e2) {
        var w2 = (e2 && e2.message) || String(e2)
        try {
          await m.update(id0, { flagged: true })
          return { ok: true, detail: 'Tag apply failed: ' + w1 + ' / ' + w2 + ' Starred instead.' }
        } catch (e3) {
          return { ok: false, detail: w1 + ' | ' + w2 + ' | ' + ((e3 && e3.message) || e3) }
        }
      }
    }
    return { ok: true, detail: 'The “Canary” message tag was applied in the list.' }
  }

  globalThis.canaryRunApplyFiledTag = canaryRunApplyFiledTag

  /** Cache tag key so popup / filing windows can call messages.update without messaging background. */
  async function cacheCanaryTagKey() {
    const g = getGecko()
    if (!g || !g.storage || !g.storage.local) return
    const r = await resolveOrCreateCanaryTagKey()
    if (r && r.key) {
      await g.storage.local.set({ canary_tag_key: r.key })
    } else if (r && r.err) {
      await g.storage.local.set({ canary_tag_key: '', canary_tag_key_err: r.err })
    }
  }

  void cacheCanaryTagKey()
})()
