export function uploadScanLabel(file: { scan_state?: string }): string | null {
  switch (file.scan_state) {
    case 'pending': return 'Security check pending'
    case 'blocked': return 'Blocked by document security'
    case 'error': return 'Security check incomplete'
    default: return null
  }
}
export function uploadIsUnavailable(file: { scan_state?: string }): boolean {
  return Boolean(uploadScanLabel(file))
}
