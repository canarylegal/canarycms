import type { AdminAuditEvent, AdminUserPublic } from './types'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

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
