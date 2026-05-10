/**
 * Case folder_path is slash-separated. Encode each segment with encodeURIComponent so a
 * single folder can be named e.g. "A/B" (stored as "A%2FB") without creating nested A + B.
 */

export function encodeFolderPathSegment(segment: string): string {
  return encodeURIComponent(segment)
}

export function decodeFolderPathSegment(segment: string): string {
  let cur = segment
  for (let i = 0; i < 6; i++) {
    try {
      const next = decodeURIComponent(cur)
      if (next === cur) break
      cur = next
    } catch {
      break
    }
  }
  return cur
}

export function splitFolderPath(path: string): string[] {
  return (path || '').split('/').filter(Boolean)
}

/** Append a user-visible folder name as one encoded segment under parent (parent is storage form). */
export function joinFolderPath(parent: string, segment: string): string {
  const enc = encodeFolderPathSegment(segment.trim())
  if (!enc) return parent
  return parent ? `${parent}/${enc}` : enc
}

/** Decode every segment for UI labels (breadcrumb, move menu, confirm text). */
export function decodeFolderPathForDisplay(path: string): string {
  return splitFolderPath(path).map(decodeFolderPathSegment).join('/')
}
