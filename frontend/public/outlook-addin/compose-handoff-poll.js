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

  async function resolveHandoffSubject(token, bundle, caseId) {
    const shared = sh()
    const apply = applyApi()
    if (!bundle) return bundle

    if (apply && apply.resolveComposeSubject) {
      const fromBundle = apply.resolveComposeSubject(bundle)
      const rawSubject = bundle.subject != null ? String(bundle.subject) : ''
      const stripped = apply.stripLegacySubjectToken ? apply.stripLegacySubjectToken(rawSubject) : rawSubject
      if (fromBundle && fromBundle !== stripped) {
        bundle.subject = fromBundle
        return bundle
      }
    }

    if (!caseId || !token) return bundle

    let caseData = null
    try {
      const res = await fetch(shared.apiRoot() + '/cases/' + encodeURIComponent(String(caseId)), {
        headers: shared.authHeaders(token),
      })
      caseData = await res.json().catch(function () {
        return null
      })
      if (!res.ok) caseData = null
    } catch (_) {}

    if (!caseData) return bundle

    let matterDesc =
      caseData.matter_description != null ? String(caseData.matter_description).trim() : ''
    if (!matterDesc && shared.matterLabel) {
      const label = shared.matterLabel(caseData)
      const parts = label.split(' — ')
      if (parts.length > 1) matterDesc = parts[parts.length - 1].trim()
    }
    if (!matterDesc) return bundle

    const hasPrecedent = !!(
      bundle.precedent_id ||
      bundle.applied_precedent_id ||
      bundle.precedent_applied
    )
    // Canary web handoffs often omit precedent_id; merged body means a precedent was applied.
    const hasMergedContent = !!(bundle.body && String(bundle.body).trim())
    if (hasPrecedent || hasMergedContent) {
      bundle.subject = matterDesc
      bundle.matter_description = matterDesc
    }
    return bundle
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

      const caseId = bundle.case_id ? String(bundle.case_id) : claim.case_id ? String(claim.case_id) : ''
      let sourceFileId = null
      const atts = bundle.attachments || []
      if (atts.length && atts[0] && atts[0].file_id) {
        sourceFileId = String(atts[0].file_id)
      }
      if (caseId) {
        try {
          await syncPendingSend(token, caseId, sourceFileId)
        } catch (e) {
          await shared.persistPendingSendAsync(caseId, 86400)
          await shared.mirrorAuthToEventRuntimeAsync(token)
          console.warn('Canary handoff pending sync:', e && e.message ? e.message : e)
        }
      }

      await resolveHandoffSubject(token, bundle, caseId)

      await apply.openNewMessageFromBundle(bundle)
    } catch (e) {
      console.warn('Canary Outlook compose handoff:', e && e.message ? e.message : e)
    } finally {
      busy = false
    }
  }

  function startPolling() {
    if (timer != null) return
    timer = setInterval(function () {
      void tryClaimAndOpen()
    }, POLL_MS)
    void tryClaimAndOpen()
  }

  Office.onReady(function () {
    startPolling()
  })
})()
