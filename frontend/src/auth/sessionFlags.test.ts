import { describe, expect, it } from 'vitest'
import type { UserPublic } from '../types'
import {
  sessionNeedsPasswordChange,
  sessionNeedsVerifiedSecondFactor,
  userNeedsSecondFactorSetup,
} from './sessionFlags'

function user(partial: Partial<UserPublic> = {}): UserPublic {
  return {
    id: 'u1',
    email: 'a@b.co',
    display_name: 'Ada',
    role: 'user',
    is_active: true,
    is_2fa_enabled: false,
    ...partial,
  }
}

describe('sessionFlags', () => {
  it('requires second-factor setup when org policy says so and user has neither TOTP nor passkeys', () => {
    expect(userNeedsSecondFactorSetup(user({ organization_requires_second_factor: true }))).toBe(true)
    expect(
      userNeedsSecondFactorSetup(user({ organization_requires_second_factor: true, is_2fa_enabled: true })),
    ).toBe(false)
    expect(
      userNeedsSecondFactorSetup(user({ organization_requires_second_factor: true, has_passkeys: true })),
    ).toBe(false)
  })

  it('never forces 2FA setup / session gates for master recovery', () => {
    const me = user({
      is_master_recovery: true,
      organization_requires_second_factor: true,
      session_second_factor_verified: false,
      session_password_change_required: true,
    })
    expect(userNeedsSecondFactorSetup(me)).toBe(false)
    expect(sessionNeedsVerifiedSecondFactor(me)).toBe(false)
    expect(sessionNeedsPasswordChange(me)).toBe(false)
  })

  it('detects unverified second factor and required password change', () => {
    expect(sessionNeedsVerifiedSecondFactor(user({ session_second_factor_verified: false }))).toBe(true)
    expect(sessionNeedsVerifiedSecondFactor(user({ session_second_factor_verified: true }))).toBe(false)
    expect(sessionNeedsPasswordChange(user({ session_password_change_required: true }))).toBe(true)
    expect(sessionNeedsPasswordChange(user())).toBe(false)
  })
})
