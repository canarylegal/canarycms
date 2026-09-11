import { userIsMasterRecovery, type UserPublic } from '../types'

export function userNeedsSecondFactorSetup(me: UserPublic): boolean {
  if (userIsMasterRecovery(me)) return false
  return Boolean(me.organization_requires_second_factor && !me.is_2fa_enabled && !me.has_passkeys)
}

/** JWT/session did not satisfy org “verified second factor at sign-in” (passkey or password + authenticator). */
export function sessionNeedsVerifiedSecondFactor(me: UserPublic): boolean {
  if (userIsMasterRecovery(me)) return false
  return me.session_second_factor_verified === false
}

export function sessionNeedsPasswordChange(me: UserPublic): boolean {
  if (userIsMasterRecovery(me)) return false
  return me.session_password_change_required === true
}
