import type { FeeScaleOut, MatterHeadTypeOut } from './types'

export type FeeScaleScopeLevel = 0 | 1 | 2

export type FeeScaleGlobalBlock = {
  kind: 'global'
  scales: FeeScaleOut[]
}

export type FeeScaleMatterBlock = {
  kind: 'matter'
  headId: string
  headName: string
  headScales: FeeScaleOut[]
  subGroups: { subId: string; subName: string; scales: FeeScaleOut[] }[]
}

export type FeeScaleOrphanBlock = {
  kind: 'orphan'
  scales: FeeScaleOut[]
}

export type FeeScaleTreeBlock = FeeScaleGlobalBlock | FeeScaleMatterBlock | FeeScaleOrphanBlock

function sortByName(a: FeeScaleOut, b: FeeScaleOut): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
}

/** Build a nested fee scale tree grouped by scope (global → matter head → sub-type). */
export function buildFeeScaleTree(items: FeeScaleOut[], matterHeads: MatterHeadTypeOut[]): FeeScaleTreeBlock[] {
  const global: FeeScaleOut[] = []
  const headOnly = new Map<string, FeeScaleOut[]>()
  const subSpecific = new Map<string, FeeScaleOut[]>()

  for (const item of items) {
    if (!item.matter_head_type_id && !item.matter_sub_type_id) {
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

  const blocks: FeeScaleTreeBlock[] = []
  if (global.length) {
    blocks.push({ kind: 'global', scales: [...global].sort(sortByName) })
  }

  const sortedHeads = [...matterHeads].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
  )
  const knownHeadIds = new Set<string>()
  const knownSubIds = new Set<string>()

  for (const head of sortedHeads) {
    knownHeadIds.add(head.id)
    const headScales = (headOnly.get(head.id) ?? []).sort(sortByName)
    const subGroups: FeeScaleMatterBlock['subGroups'] = []

    const sortedSubs = [...head.sub_types].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
    )
    for (const sub of sortedSubs) {
      knownSubIds.add(sub.id)
      const scales = (subSpecific.get(sub.id) ?? []).sort(sortByName)
      if (scales.length) {
        subGroups.push({ subId: sub.id, subName: sub.name, scales })
      }
    }

    if (headScales.length || subGroups.length) {
      blocks.push({
        kind: 'matter',
        headId: head.id,
        headName: head.name,
        headScales,
        subGroups,
      })
    }
  }

  const orphans: FeeScaleOut[] = []
  for (const [headId, scales] of headOnly) {
    if (!knownHeadIds.has(headId)) orphans.push(...scales)
  }
  for (const [subId, scales] of subSpecific) {
    if (!knownSubIds.has(subId)) orphans.push(...scales)
  }
  if (orphans.length) {
    blocks.push({ kind: 'orphan', scales: [...orphans].sort(sortByName) })
  }

  return blocks
}

/** @deprecated Use buildFeeScaleTree for hierarchical display. */
export type FeeScaleGroup = {
  key: string
  label: string
  items: FeeScaleOut[]
}

export function groupFeeScales(items: FeeScaleOut[], matterHeads: MatterHeadTypeOut[]): FeeScaleGroup[] {
  return buildFeeScaleTree(items, matterHeads).flatMap((block) => {
    if (block.kind === 'global') {
      return [{ key: 'global', label: 'Global — all cases', items: block.scales }]
    }
    if (block.kind === 'orphan') {
      return [{ key: 'other', label: 'Other', items: block.scales }]
    }
    const out: FeeScaleGroup[] = []
    if (block.headScales.length) {
      out.push({
        key: `head-${block.headId}`,
        label: `${block.headName} — all sub-types`,
        items: block.headScales,
      })
    }
    for (const sg of block.subGroups) {
      out.push({
        key: `sub-${sg.subId}`,
        label: `${block.headName} — ${sg.subName}`,
        items: sg.scales,
      })
    }
    return out
  })
}
