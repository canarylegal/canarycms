import { useEffect, useRef, useState } from 'react'
import {
  DEFAULT_ACCENT,
  getThemePreferences,
  saveThemePreferences,
  themeFromAppearance,
  type ThemePreferences,
} from './theme'
import type { UserAppearanceOut, UserPublic } from './types'

/** Apply the signed-in user's server appearance and keep localStorage in sync for editor tabs. */
export function useServerAppearance(me: UserPublic | null | undefined, token: string | null) {
  const migratedRef = useRef(false)

  useEffect(() => {
    if (!me?.appearance) return
    const server = themeFromAppearance(me.appearance)
    const local = getThemePreferences()
    const serverIsDefault =
      !server.font && server.accent === DEFAULT_ACCENT && server.mode === 'light' && !server.pageBg
    const localHasCustom =
      !!local.font || local.mode === 'dark' || local.accent !== DEFAULT_ACCENT || !!local.pageBg

    if (!migratedRef.current && token && serverIsDefault && localHasCustom) {
      migratedRef.current = true
      void persistUserAppearance(token, local).catch(() => {
        saveThemePreferences(server)
      })
      return
    }

    saveThemePreferences(server)
  }, [me?.appearance, token])
}

export async function persistUserAppearance(
  token: string,
  prefs: ThemePreferences,
): Promise<UserAppearanceOut> {
  const { apiFetch } = await import('./api')
  const user = await apiFetch<UserPublic>('/users/me/appearance', {
    token,
    method: 'PUT',
    json: {
      font: prefs.font,
      accent: prefs.accent,
      mode: prefs.mode,
      page_bg: prefs.pageBg,
    },
  })
  const appearance = user.appearance ?? { font: '', accent: DEFAULT_ACCENT, mode: 'light' as const, page_bg: '' }
  saveThemePreferences(themeFromAppearance(appearance))
  return appearance
}

export function useAppearanceFormState(account: UserPublic | null) {
  const initial = getThemePreferences()
  const [appFont, setAppFont] = useState(initial.font)
  const [appAccent, setAppAccent] = useState(initial.accent)
  const [appPageBg, setAppPageBg] = useState(initial.pageBg)
  const [appMode, setAppMode] = useState<'light' | 'dark'>(initial.mode)

  useEffect(() => {
    if (!account?.appearance) return
    const p = themeFromAppearance(account.appearance)
    setAppFont(p.font)
    setAppAccent(p.accent)
    setAppPageBg(p.pageBg)
    setAppMode(p.mode)
  }, [account?.appearance])

  const prefs: ThemePreferences = {
    font: appFont,
    accent: appAccent,
    mode: appMode,
    pageBg: appPageBg,
  }

  return {
    appFont,
    setAppFont,
    appAccent,
    setAppAccent,
    appPageBg,
    setAppPageBg,
    appMode,
    setAppMode,
    prefs,
  }
}

export { DEFAULT_ACCENT }
