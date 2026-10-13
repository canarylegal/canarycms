import type { AdminAuditEvent, AdminUserPublic } from './types'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

const ACTION_LABELS: Record<string, string> = {
  'auth.login': 'Signed in',
  'auth.login.passkey': 'Signed in with passkey',
  'case.create': 'Created matter',
  'case.update': 'Updated matter',
  'case.file.upload': 'Uploaded file',
  'case.file.rename': 'Renamed file',
  'case.file.delete': 'Deleted file',
  'case.file.move': 'Moved file',
  'case.file.download': 'Downloaded file',
  'case.file.open': 'Opened file',
  'case.file.onlyoffice_open': 'Opened document in editor',
  'case.file.onlyoffice_callback': 'Saved document from editor',
  'case.file.compose_quote': 'Created quote document',
  'case.file.compose_office': 'Created document from precedent',
  'case.file.compose_publish': 'Published composed document',
  'case.file.compose_discard': 'Discarded composed document',
  'case.folder.create': 'Created folder',
  'case.folder.rename': 'Renamed folder',
  'case.folder.delete': 'Deleted folder',
  'case.task.create': 'Created task',
  'case.task.update': 'Updated task',
  'case.task.delete': 'Deleted task',
  'ledger.post': 'Posted to ledger',
  'ledger.approve': 'Approved ledger posting',
  'invoice.create': 'Created invoice',
  'invoice.approve': 'Approved invoice',
  'invoice.void': 'Voided invoice',
}

function looksLikeUuid(value: string): boolean {
  return UUID_RE.test(value.trim())
}

function isUsableDisplayName(value: string | null | undefined): value is string {
  const trimmed = value?.trim()
  return Boolean(trimmed && !looksLikeUuid(trimmed))
}

export function actorLabel(e: AdminAuditEvent, usersById: Map<string, AdminUserPublic>): string {
  if (isUsableDisplayName(e.actor_display_name)) {
    return e.actor_initials ? `${e.actor_display_name} (${e.actor_initials})` : e.actor_display_name
  }
  if (e.actor_user_id) {
    const u = usersById.get(e.actor_user_id)
    if (u?.display_name && !looksLikeUuid(u.display_name)) {
      return u.initials ? `${u.display_name} (${u.initials})` : u.display_name
    }
    return 'Former user'
  }
  if (e.actor_initials && !looksLikeUuid(e.actor_initials)) return e.actor_initials
  return 'System'
}

/** Everyday label for the Action column; raw key stays available via title. */
export function actionLabel(action: string): string {
  if (ACTION_LABELS[action]) return ACTION_LABELS[action]
  return action.replace(/\./g, ' · ').replace(/_/g, ' ')
}
