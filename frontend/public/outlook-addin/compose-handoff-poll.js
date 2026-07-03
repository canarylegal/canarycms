/* global Office */
'use strict'
;(function () {
  const POLL_MS = 4000

  function sh() {
    return globalThis.canaryOutlookShared
  }

  function applyApi() {
    return globalThis.canaryOutlookApplyCompose
  }

  let busy = false
  let timer = null

  async function syncPendingSend(token, caseId, sourceFileId) {
    if (!caseId) return
    const payload = {
      case_id: caseId,
      source_file_id: sourceFileId || null,
      ttl_seconds: 86400,
    }
    const res = await fetch(sh().apiRoot() + '/mail-plugin/pending-send', {
      method: 'PUT',
      headers: sh().jsonAuthHeaders(token),
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const body = await res.json().catch(function () {
        return null
      })
      const detail = body && body.detail
      throw new Error(typeof detail === 'string' ? detail : 'Could not set pending send matter.')
    }
    await sh().persistPendingSendAsync(caseId, 86400)
    await sh().mirrorAuthToEventRuntimeAsync(token)
  }

  async function tryClaimAndOpen() {
    if (busy) return
    const shared = sh()
    const apply = applyApi()
    if (!shared || !apply || typeof apply.openNewMessageFromBundle !== 'function') return
    const token = shared.getToken()
    if (!token) return
    busy = true
    try {
      const claimRes = await fetch(shared.apiRoot() + '/mail-plugin/pending-compose-handoff/claim', {
        method: 'POST',
        headers: shared.authHeaders(token),
      })
      const claim = await claimRes.json().catch(function () {
        return null
      })
      if (!claimRes.ok || !claim || !claim.active || !claim.handoff_token) return

      const handoffRes = await fetch(
        shared.apiRoot() + '/mail-plugin/compose-handoff/' + encodeURIComponent(String(claim.handoff_token)),
        { headers: shared.authHeaders(token) },
      )
      const bundle = await handoffRes.json().catch(function () {
        return null
      })
      if (!handoffRes.ok || !bundle) return

      await apply.openNewMessageFromBundle(bundle)

      const caseId = bundle.case_id ? String(bundle.case_id) : claim.case_id ? String(claim.case_id) : ''
      let sourceFileId = null
      const atts = bundle.attachments || []
      if (atts.length && atts[0] && atts[0].file_id) {
        sourceFileId = String(atts[0].file_id)
      }
      if (caseId) {
        await syncPendingSend(token, caseId, sourceFileId)
      }
    } catch (e) {
      console.warn('Canary Outlook compose handoff:', e && e.message ? e.message : e)
    } finally {
      busy = false
    }
  }

  async function syncServerPendingFromApi(token) {
    if (!token || !sh()) return
    try {
      const res = await fetch(sh().apiRoot() + '/mail-plugin/pending-send', {
        headers: sh().authHeaders(token),
      })
      const body = await res.json().catch(function () {
        return null
      })
      if (!res.ok || !body || !body.active || !body.case_id) return
      let ttl = 86400
      if (body.expires_at) {
        try {
          const ms = new Date(body.expires_at).getTime() - Date.now()
          if (ms > 60000) ttl = Math.ceil(ms / 1000)
        } catch (_) {}
      }
      await sh().persistPendingSendAsync(String(body.case_id), ttl)
      await sh().mirrorAuthToEventRuntimeAsync(token)
    } catch (_) {
      /* best-effort */
    }
  }

  function startPolling() {
    if (timer != null) return
    timer = setInterval(function () {
      void tryClaimAndOpen()
      const token = sh() && sh().getToken ? sh().getToken() : ''
      if (token) void syncServerPendingFromApi(token)
    }, POLL_MS)
    void tryClaimAndOpen()
    const token = sh() && sh().getToken ? sh().getToken() : ''
    if (token) void syncServerPendingFromApi(token)
  }

  Office.onReady(function () {
    startPolling()
  })
})()
