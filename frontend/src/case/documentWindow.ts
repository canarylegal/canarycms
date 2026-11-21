/** Prefix offsets and binary lookup keep variable-height document windows predictable. */
export function documentOffsets(keys: string[], heights: ReadonlyMap<string, number>, estimate: number): number[] {
  const offsets = [0]
  for (const key of keys) offsets.push(offsets[offsets.length - 1] + (heights.get(key) ?? estimate))
  return offsets
}
export function documentWindow(offsets: number[], top: number, height: number, overscan = 8) {
  const count = offsets.length - 1
  const find = (position: number) => {
    let low = 0, high = count
    while (low < high) {
      const middle = (low + high) >>> 1
      if (offsets[middle + 1] <= position) low = middle + 1
      else high = middle
    }
    return low
  }
  const start = Math.max(0, Math.min(count, find(Math.max(0, top))) - overscan)
  const end = Math.min(count, find(Math.max(0, top) + height) + 1 + overscan)
  return {start, end, before: offsets[start], after: offsets[count] - offsets[end]}
}
