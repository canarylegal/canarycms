import type { ApiError } from './api'
import type { ConfirmChoice } from './DialogProvider'

export const PORTAL_EMAIL_CONFLICT_CODE = 'portal_email_conflict'

export type PortalEmailConflictDetail = {
  code: string
  message: string
  other_contact_id: string
  other_contact_name: string
  other_email: string
  other_grant_count?: number
}

export type PortalConflictResolution = 'join_existing' | 'revoke_other'

type AskConfirmChoice = (opts: {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  secondaryLabel: string
  danger?: boolean
}) => Promise<ConfirmChoice>

export function parsePortalEmailConflict(err: unknown): PortalEmailConflictDetail | null {
  const e = err as ApiError | undefined
  if (!e || e.status !== 409 || !e.body || typeof e.body !== 'object') return null
  const detail = (e.body as { detail?: unknown }).detail
  if (!detail || typeof detail !== 'object') return null
  const d = detail as Record<string, unknown>
  if (d.code !== PORTAL_EMAIL_CONFLICT_CODE) return null
  if (typeof d.other_contact_id !== 'string' || typeof d.other_contact_name !== 'string') return null
  return {
    code: PORTAL_EMAIL_CONFLICT_CODE,
    message: typeof d.message === 'string' ? d.message : 'This e-mail already has a portal login on another contact.',
    other_contact_id: d.other_contact_id,
    other_contact_name: d.other_contact_name,
    other_email: typeof d.other_email === 'string' ? d.other_email : '',
    other_grant_count: typeof d.other_grant_count === 'number' ? d.other_grant_count : undefined,
  }
}

/** Staff-facing copy when a portal e-mail conflict blocks an action. */
export function portalEmailConflictStaffMessage(
  conflict: PortalEmailConflictDetail,
  context: 'grant' | 'email_change' | 'delivery' = 'grant',
): string {
  const who = conflict.other_contact_name || 'Another contact'
  const email = conflict.other_email || 'this e-mail'
  if (context === 'email_change') {
    return (
      `${who} already has an active client portal login for ${email}. ` +
      `Use a different e-mail, revoke portal access on that contact first, or merge the duplicate contacts.`
    )
  }
  if (context === 'delivery') {
    return (
      `Cannot send via portal: ${who} already has an active client portal login for ${email}. ` +
      `Resolve the login on the contact card first (join existing or revoke the earlier one), then try again.`
    )
  }
  return conflict.message
}

/** Forced choice when granting portal access would create a second login for the same e-mail. */
export async function choosePortalEmailConflictResolution(
  askConfirmChoice: AskConfirmChoice,
  conflict: PortalEmailConflictDetail,
): Promise<PortalConflictResolution | null> {
  const grants =
    conflict.other_grant_count != null && conflict.other_grant_count > 0
      ? `\n\nThat contact currently has ${conflict.other_grant_count} shared folder${
          conflict.other_grant_count === 1 ? '' : 's'
        }.`
      : ''
  const result = await askConfirmChoice({
    title: 'Portal login already exists',
    message:
      `${conflict.other_contact_name} already has an active portal login for ${conflict.other_email || 'this e-mail'}.` +
      grants +
      `\n\nJoin existing login — keep that access code and use it for this contact's portal content.\n` +
      `Revoke earlier login — disable the other contact's login and issue a new code here.\n\n` +
      `You must choose one; both logins cannot stay active for the same e-mail.`,
    confirmLabel: 'Join existing login',
    secondaryLabel: 'Revoke earlier login',
    cancelLabel: 'Cancel',
    danger: true,
  })
  if (result === 'confirm') return 'join_existing'
  if (result === 'secondary') return 'revoke_other'
  return null
}
