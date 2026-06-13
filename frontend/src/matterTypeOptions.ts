import type { MatterHeadTypeOut } from './types'

export function matterHeadDropdownOptions(matterHeadTypes: MatterHeadTypeOut[]) {
  return matterHeadTypes.map((head) => ({ value: head.id, label: head.name }))
}

export function matterSubDropdownOptions(matterHeadTypes: MatterHeadTypeOut[], headTypeId: string) {
  const head = matterHeadTypes.find((h) => h.id === headTypeId)
  return (head?.sub_types ?? []).map((sub) => ({ value: sub.id, label: sub.name }))
}

export function matterHeadIdForSubType(matterHeadTypes: MatterHeadTypeOut[], subTypeId: string): string {
  if (!subTypeId) return ''
  for (const head of matterHeadTypes) {
    if (head.sub_types.some((s) => s.id === subTypeId)) return head.id
  }
  return ''
}
