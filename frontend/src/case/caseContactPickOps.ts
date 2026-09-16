import { apiFetch } from '../api'
import { LAWYER_CLIENTS_REQUIRED_MSG } from './CaseContactsDocForms'
import { LAWYERS_TYPE_SLUG } from './caseDetailHelpers'
import type { ContactOut } from '../types'

/** Link a global contact onto the matter when the picker requested it. Returns an error message or null. */
export async function linkPickedGlobalContactIfNeeded(args: {
  caseId: string
  token: string
  pickSelectedContact: ContactOut | null
  pickLinkGlobal: boolean
  pickLinkType: string
  pickLawyerClientIds: string[]
  onRefresh: () => void
}): Promise<string | null> {
  const {
    caseId,
    token,
    pickSelectedContact,
    pickLinkGlobal,
    pickLinkType,
    pickLawyerClientIds,
    onRefresh,
  } = args
  if (!pickSelectedContact || !pickLinkGlobal) return null
  if (!pickLinkType.trim()) {
    return 'Contact type is required when linking to this matter.'
  }
  if (pickLinkType.trim().toLowerCase() === LAWYERS_TYPE_SLUG && pickLawyerClientIds.length < 1) {
    return LAWYER_CLIENTS_REQUIRED_MSG
  }
  const linkJson: Record<string, unknown> = {
    contact_id: pickSelectedContact.id,
    matter_contact_type: pickLinkType.trim(),
    matter_contact_reference: null,
  }
  if (pickLinkType.trim().toLowerCase() === LAWYERS_TYPE_SLUG) {
    linkJson.lawyer_client_ids = pickLawyerClientIds
  }
  await apiFetch(`/cases/${caseId}/contacts`, {
    token,
    json: linkJson,
  })
  onRefresh()
  return null
}
