import type { MatterHeadTypeOut, PrecedentOut } from './types'

export const SYSTEM_PRECEDENT_REFERENCES = new Set([
  'BLANK_LETTER',
  'BLANK_EMAIL',
  'INVOICE_TEMPLATE',
  'COMPLETION_STATEMENT',
  'QUOTE_TEMPLATE',
  'QUOTE_EMAIL',
])

export type PrecedentKindFilter = 'all' | 'letter' | 'email' | 'document'

export type PrecedentListFilters = {
  search: string
  kind: PrecedentKindFilter
}

export function isSystemPrecedent(
  p: PrecedentOut,
  systemRefs: ReadonlySet<string> = SYSTEM_PRECEDENT_REFERENCES,
): boolean {
  return systemRefs.has(p.reference)
}

export function precedentMatchesListFilters(p: PrecedentOut, filters: PrecedentListFilters): boolean {
  if (filters.kind !== 'all' && p.kind !== filters.kind) return false
  const q = filters.search.trim().toLowerCase()
  if (!q) return true
  return p.name.toLowerCase().includes(q) || p.reference.toLowerCase().includes(q)
}

function sortByName(a: PrecedentOut, b: PrecedentOut): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
}

export type PrecedentCategoryGroup = {
  categoryId: string
  categoryName: string
  precedents: PrecedentOut[]
}

export type PrecedentSubTypeBlock = {
  subId: string
  subName: string
  uncategorised: PrecedentOut[]
  categoryGroups: PrecedentCategoryGroup[]
}

export type PrecedentMatterBlock = {
  kind: 'matter'
  headId: string
  headName: string
  headPrecedents: PrecedentOut[]
  subGroups: PrecedentSubTypeBlock[]
}

export type PrecedentSystemBlock = {
  kind: 'system'
  precedents: PrecedentOut[]
}

export type PrecedentGlobalBlock = {
  kind: 'global'
  precedents: PrecedentOut[]
}

export type PrecedentOrphanBlock = {
  kind: 'orphan'
  precedents: PrecedentOut[]
}

export type PrecedentTreeBlock =
  | PrecedentSystemBlock
  | PrecedentGlobalBlock
  | PrecedentMatterBlock
  | PrecedentOrphanBlock

function buildSubTypeBlock(subId: string, subName: string, rows: PrecedentOut[]): PrecedentSubTypeBlock | null {
  const uncategorised = rows.filter((p) => !p.category_id).sort(sortByName)
  const byCategory = new Map<string, PrecedentOut[]>()
  for (const p of rows) {
    if (!p.category_id) continue
    const list = byCategory.get(p.category_id) ?? []
    list.push(p)
    byCategory.set(p.category_id, list)
  }
  const categoryGroups: PrecedentCategoryGroup[] = [...byCategory.entries()]
    .map(([categoryId, precedents]) => ({
      categoryId,
      categoryName: precedents[0]?.category_name?.trim() || 'Category',
      precedents: [...precedents].sort(sortByName),
    }))
    .sort((a, b) => a.categoryName.localeCompare(b.categoryName, undefined, { sensitivity: 'base' }))

  if (!uncategorised.length && !categoryGroups.length) return null
  return { subId, subName, uncategorised, categoryGroups }
}

/** Group precedents for Admin → Precedents (system block ignores search/kind filters). */
export function buildPrecedentTree(
  items: PrecedentOut[],
  matterHeads: MatterHeadTypeOut[],
  filters: PrecedentListFilters,
  systemRefs: ReadonlySet<string> = SYSTEM_PRECEDENT_REFERENCES,
): PrecedentTreeBlock[] {
  const system = items.filter((p) => isSystemPrecedent(p, systemRefs)).sort(sortByName)
  const custom = items.filter((p) => !isSystemPrecedent(p, systemRefs))
  const filtered = custom.filter((p) => precedentMatchesListFilters(p, filters))

  const global: PrecedentOut[] = []
  const headOnly = new Map<string, PrecedentOut[]>()
  const subSpecific = new Map<string, PrecedentOut[]>()

  for (const item of filtered) {
    if (!item.matter_head_type_id && !item.matter_sub_type_id && !item.category_id) {
      global.push(item)
    } else if (item.matter_sub_type_id) {
      const list = subSpecific.get(item.matter_sub_type_id) ?? []
      list.push(item)
      subSpecific.set(item.matter_sub_type_id, list)
    } else if (item.matter_head_type_id) {
      const list = headOnly.get(item.matter_head_type_id) ?? []
      list.push(item)
      headOnly.set(item.matter_head_type_id, list)
    }
  }

  const blocks: PrecedentTreeBlock[] = []

  if (system.length) {
    blocks.push({ kind: 'system', precedents: system })
  }
  if (global.length) {
    blocks.push({ kind: 'global', precedents: [...global].sort(sortByName) })
  }

  const sortedHeads = [...matterHeads].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
  )
  const knownHeadIds = new Set<string>()
  const knownSubIds = new Set<string>()

  for (const head of sortedHeads) {
    knownHeadIds.add(head.id)
    const headPrecedents = (headOnly.get(head.id) ?? []).sort(sortByName)
    const subGroups: PrecedentSubTypeBlock[] = []

    const sortedSubs = [...head.sub_types].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
    )
    for (const sub of sortedSubs) {
      knownSubIds.add(sub.id)
      const rows = subSpecific.get(sub.id)
      if (!rows?.length) continue
      const block = buildSubTypeBlock(sub.id, sub.name, rows)
      if (block) subGroups.push(block)
    }

    if (headPrecedents.length || subGroups.length) {
      blocks.push({
        kind: 'matter',
        headId: head.id,
        headName: head.name,
        headPrecedents,
        subGroups,
      })
    }
  }

  const orphans: PrecedentOut[] = []
  for (const [headId, rows] of headOnly) {
    if (!knownHeadIds.has(headId)) orphans.push(...rows)
  }
  for (const [subId, rows] of subSpecific) {
    if (!knownSubIds.has(subId)) orphans.push(...rows)
  }
  if (orphans.length) {
    blocks.push({ kind: 'orphan', precedents: [...orphans].sort(sortByName) })
  }

  return blocks
}

export function countFilteredCustomPrecedents(
  items: PrecedentOut[],
  filters: PrecedentListFilters,
  systemRefs: ReadonlySet<string> = SYSTEM_PRECEDENT_REFERENCES,
): number {
  return items.filter((p) => !isSystemPrecedent(p, systemRefs) && precedentMatchesListFilters(p, filters)).length
}
