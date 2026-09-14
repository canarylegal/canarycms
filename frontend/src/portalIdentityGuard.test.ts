import { describe, expect, it, vi } from 'vitest'
import {
  choosePortalActionOnIdentityChange,
  contactIdentityFieldsChanged,
} from './portalIdentityGuard'

describe('portalIdentityGuard', () => {
  it('detects type and name identity changes', () => {
    expect(
      contactIdentityFieldsChanged(
        { type: 'person', first_name: 'Ann', middle_name: null, last_name: 'Lee' },
        { type: 'person', first_name: 'Ann', middle_name: '', last_name: 'Lee' },
      ),
    ).toBe(false)
    expect(
      contactIdentityFieldsChanged(
        { type: 'person', first_name: 'Ann', middle_name: null, last_name: 'Lee' },
        { type: 'person', first_name: 'Bob', middle_name: null, last_name: 'Lee' },
      ),
    ).toBe(true)
    expect(
      contactIdentityFieldsChanged(
        { type: 'person', first_name: 'Ann', middle_name: null, last_name: 'Lee' },
        { type: 'organisation', first_name: 'Ann', middle_name: null, last_name: 'Lee' },
      ),
    ).toBe(true)
  })

  it('skips prompt when unchanged or no portal access', async () => {
    const askConfirmChoice = vi.fn()
    await expect(
      choosePortalActionOnIdentityChange(askConfirmChoice, {
        identityChanged: false,
        portalAccessActive: true,
      }),
    ).resolves.toBe('save_keep')
    await expect(
      choosePortalActionOnIdentityChange(askConfirmChoice, {
        identityChanged: true,
        portalAccessActive: false,
      }),
    ).resolves.toBe('save_keep')
    expect(askConfirmChoice).not.toHaveBeenCalled()
  })

  it('maps confirm outcomes', async () => {
    await expect(
      choosePortalActionOnIdentityChange(async () => 'confirm', {
        identityChanged: true,
        portalAccessActive: true,
      }),
    ).resolves.toBe('save_revoke')
    await expect(
      choosePortalActionOnIdentityChange(async () => 'secondary', {
        identityChanged: true,
        portalAccessActive: true,
      }),
    ).resolves.toBe('save_keep')
    await expect(
      choosePortalActionOnIdentityChange(async () => 'cancel', {
        identityChanged: true,
        portalAccessActive: true,
      }),
    ).resolves.toBe('cancel')
  })
})
