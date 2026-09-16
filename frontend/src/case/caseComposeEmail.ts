import { apiFetch } from '../api'
import {
  appendOutlookWebAuthHintsForNav,
  OWA_MESSAGE_WINDOW_FEATURES,
  openM365ComposeDraft,
  OWA_MAIL_WINDOW_NAME,
} from '../emailClient'
import {
  buildMailtoComposeUrl,
  buildOutlookWebComposeUrl,
  normalizeComposeQueryPlusAsSpaces,
  shouldUseGraphDraftForMatterEmail,
} from '../emailLauncher'
import type {
  CaseEmailDraftM365Out,
  CaseEmailMailtoOut,
  OutlookPluginPendingComposeHandoffOut,
  UserPublic,
} from '../types'

export type ComposeMatterEmailArgs = {
  caseId: string
  token: string
  docFolder: string
  currentUser?: UserPublic | null
  precedentId: string | null
  caseContactId: string | null
  globalContactId: string | null
  precedentMergeAllClients: boolean
  composeOfficeRole?: 'letter' | 'document' | null
  attachmentFileIds?: string[]
  pushNotification: (message: string) => void
  setActionErr: (message: string | null) => void
}

/** Launch matter e-mail compose (Graph draft when available, else mailto / Outlook web). */
export async function composeMatterEmail({
  caseId,
  token,
  docFolder,
  currentUser,
  precedentId,
  caseContactId,
  globalContactId,
  precedentMergeAllClients,
  composeOfficeRole,
  attachmentFileIds = [],
  pushNotification,
  setActionErr,
}: ComposeMatterEmailArgs): Promise<void> {
  const composePayload = {
    folder: docFolder,
    precedent_id: precedentId,
    case_contact_id: caseContactId,
    global_contact_id: globalContactId,
    precedent_merge_all_clients: precedentMergeAllClients,
    compose_office_role: composeOfficeRole ?? null,
    attachment_file_ids: attachmentFileIds,
  }

  const useGraphDraft = shouldUseGraphDraftForMatterEmail(currentUser, attachmentFileIds)

  if (useGraphDraft) {
    try {
      const res = await apiFetch<CaseEmailDraftM365Out>(`/cases/${caseId}/files/email-drafts/m365`, {
        token,
        json: composePayload,
      })
      try {
        await apiFetch(`/mail-plugin/pending-send`, {
          token,
          method: 'PUT',
          json: {
            case_id: caseId,
            source_file_id: attachmentFileIds[0] ?? null,
            ttl_seconds: 86400,
          },
        })
      } catch {
        /* Best-effort: add-in send capture works without this if user files manually. */
      }
      const attachNames = (res.attachment_files ?? []).map((f) => f.filename).filter(Boolean)
      const attachLabel =
        attachNames.length === 1
          ? attachNames[0]
          : attachNames.length > 1
            ? `${attachNames.length} files`
            : res.attachment_count === 1
              ? '1 file'
              : res.attachment_count
                ? `${res.attachment_count} files`
                : 'attachments'
      const launchPref = currentUser?.email_launch_preference ?? 'desktop'
      if (launchPref === 'outlook_web') {
        const opened = openM365ComposeDraft(res, currentUser?.email?.trim() || null)
        if (!opened) {
          setActionErr('Your browser blocked opening Outlook. Allow pop-ups for this site.')
          return
        }
        pushNotification(
          `Outlook draft created with ${attachLabel} attached. Review and send from the draft window.`,
        )
      } else {
        if (res.compose_handoff_token) {
          try {
            await apiFetch<OutlookPluginPendingComposeHandoffOut>(`/mail-plugin/pending-compose-handoff`, {
              token,
              method: 'PUT',
              json: {
                handoff_token: res.compose_handoff_token,
                ttl_seconds: 3600,
              },
            })
          } catch {
            /* Best-effort: user can open Drafts or use Compose from matter manually. */
          }
        }
        pushNotification(
          `Draft created with ${attachLabel} attached. If Outlook is open with the Canary add-in signed in, a compose window should appear shortly — otherwise open Drafts in Outlook or use Compose from matter in the add-in.`,
        )
      }
      return
    } catch (e: unknown) {
      const err = e as { status?: number; message?: string }
      if (err.status !== 503) {
        throw e
      }
      pushNotification(
        'Microsoft Graph drafts are unavailable — opening compose without automatic attachment.',
      )
    }
  }

  const res = await apiFetch<CaseEmailMailtoOut>(`/cases/${caseId}/files/email-mailto`, {
    token,
    json: composePayload,
  })
  try {
    await apiFetch(`/mail-plugin/pending-send`, {
      token,
      method: 'PUT',
      json: {
        case_id: caseId,
        source_file_id: attachmentFileIds[0] ?? null,
        ttl_seconds: 86400,
      },
    })
  } catch {
    /* Best-effort: add-in send capture works without this if user files manually. */
  }
  const launchPref = currentUser?.email_launch_preference ?? 'desktop'
  if (launchPref === 'outlook_web') {
    let url = buildOutlookWebComposeUrl(currentUser?.email_outlook_web_url, {
      to: res.to,
      subject: res.subject,
      body: res.body,
    })
    url = appendOutlookWebAuthHintsForNav(url, currentUser?.email?.trim() || null)
    url = normalizeComposeQueryPlusAsSpaces(url)
    const w = window.open(url, OWA_MAIL_WINDOW_NAME, OWA_MESSAGE_WINDOW_FEATURES)
    if (!w) {
      setActionErr('Your browser blocked opening Outlook. Allow pop-ups for this site.')
      return
    }
  } else {
    const a = document.createElement('a')
    a.href = buildMailtoComposeUrl({ to: res.to, subject: res.subject, body: res.body })
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }
}
