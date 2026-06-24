export type LetterSalutation =
  | 'dear_first_name_informal'
  | 'dear_first_name_formal'
  | 'dear_sir_madam'
  | 'dear_sir_or_madam'
  | 'dear_sirs'
  | 'dear_firm_name'
  | 'custom'

export const CLIENT_MATTER_TYPE_SLUG = 'client'

export function defaultLetterSalutation(
  matterContactType: string,
  contactType: 'person' | 'organisation',
): LetterSalutation {
  if (contactType === 'organisation') return 'dear_sir_madam'
  if (matterContactType.trim().toLowerCase() === CLIENT_MATTER_TYPE_SLUG) return 'dear_first_name_informal'
  return 'dear_sir_madam'
}

export function letterSalutationOptions(
  matterContactType: string,
  contactType: 'person' | 'organisation',
): { value: LetterSalutation; label: string }[] {
  const isClient = matterContactType.trim().toLowerCase() === CLIENT_MATTER_TYPE_SLUG
  if (contactType === 'organisation') {
    return [
      { value: 'dear_sir_madam', label: 'Dear Sir / Madam' },
      { value: 'dear_sirs', label: 'Dear Sirs' },
      { value: 'dear_firm_name', label: 'Dear [firm name]' },
      { value: 'custom', label: 'Custom' },
    ]
  }
  if (isClient) {
    return [
      { value: 'dear_first_name_informal', label: 'Dear [name] (informal)' },
      { value: 'dear_first_name_formal', label: 'Dear [name] (formal)' },
      { value: 'custom', label: 'Custom' },
    ]
  }
  return [
    { value: 'dear_sir_madam', label: 'Dear Sir / Madam' },
    { value: 'dear_sir_or_madam', label: 'Dear Sir or Madam' },
    { value: 'custom', label: 'Custom' },
  ]
}

export function coerceLetterSalutation(
  value: string | null | undefined,
  matterContactType: string,
  contactType: 'person' | 'organisation',
): LetterSalutation {
  const allowed = new Set(letterSalutationOptions(matterContactType, contactType).map((o) => o.value))
  const raw = (value || '').trim() as LetterSalutation
  if (allowed.has(raw)) return raw
  return defaultLetterSalutation(matterContactType, contactType)
}
