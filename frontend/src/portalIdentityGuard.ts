import { apiFetch } from './api'
import type { ConfirmChoice } from './DialogProvider'
import type { ContactPortalAccessOut } from './types'

/** Fields that identify who the contact is (not address/email tweaks). */
export type ContactIdentityFields = {
  type: string
  first_name?: string | null
  middle_name?: string | null
  last_name?: string | null
}

export function contactIdentityFieldsChanged(
  before: ContactIdentityFields,
  after: ContactIdentityFields,
): boolean {
  const norm = (v: string | null | undefined) => (v ?? '').trim()
  return (
    before.type !== after.type ||
    norm(before.first_name) !== norm(after.first_name) ||
    norm(before.middle_name) !== norm(after.middle_name) ||
    norm(before.last_name) !== norm(after.last_name)
  )
}

export const PORTAL_IDENTITY_REVOKE_TITLE = 'Revoke portal access?'

export const PORTAL_IDENTITY_REVOKE_MESSAGE = `You are changing this contact's type or name, and they currently have an active Canary Portal access code.

If you are replacing this person with someone else (reusing this contact record), the existing access code will still work. The replacement person could sign in to the portal and see folders and documents that were shared with the previous contact.

If you are only correcting a spelling or updating details for the same person, you can keep the access code.

Choose carefully:
• Save and revoke access — recommended when replacing the contact
• Save and keep access — only when this is still the same person
• Don't save — leave the contact and portal code unchanged`

export type PortalIdentitySaveChoice = 'cancel' | 'save_revoke' | 'save_keep'

type AskConfirmChoice = (opts: {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  secondaryLabel: string
  danger?: boolean
}) => Promise<ConfirmChoice>

/** Prompt when identity fields change and portal access is active. */
export async function choosePortalActionOnIdentityChange(
  askConfirmChoice: AskConfirmChoice,
  opts: {
    identityChanged: boolean
    portalAccessActive: boolean
  },
): Promise<PortalIdentitySaveChoice> {
  if (!opts.identityChanged || !opts.portalAccessActive) return 'save_keep'
  const result = await askConfirmChoice({
    title: PORTAL_IDENTITY_REVOKE_TITLE,
    message: PORTAL_IDENTITY_REVOKE_MESSAGE,
    confirmLabel: 'Save and revoke access',
    secondaryLabel: 'Save and keep access',
    cancelLabel: "Don't save",
    danger: true,
  })
  if (result === 'confirm') return 'save_revoke'
  if (result === 'secondary') return 'save_keep'
  return 'cancel'
}

export async function contactHasActivePortalAccess(
  token: string,
  contactId: string,
): Promise<boolean> {
  try {
    const row = await apiFetch<ContactPortalAccessOut>(`/contacts/${contactId}/portal/access`, {
      token,
    })
    return Boolean(row.has_access)
  } catch {
    return false
  }
}

export async function contactHasActiveMatterPortalAccess(
  token: string,
  caseId: string,
  contactId: string,
): Promise<boolean> {
  try {
    const row = await apiFetch<ContactPortalAccessOut>(
      `/cases/${caseId}/contacts/${contactId}/matter-portal/access`,
      { token },
    )
    return Boolean(row.has_access)
  } catch {
    return false
  }
}

export async function revokeContactPortalAccess(token: string, contactId: string): Promise<void> {
  await apiFetch(`/contacts/${contactId}/portal/access`, { token, method: 'DELETE' })
}

export async function revokeMatterPortalAccess(
  token: string,
  caseId: string,
  contactId: string,
): Promise<void> {
  await apiFetch(`/cases/${caseId}/contacts/${contactId}/matter-portal/access`, {
    token,
    method: 'DELETE',
  })
}
