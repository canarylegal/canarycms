/** Keep uncertain document requests identifiable across a manual retry or reload. */
export async function documentOperationRetry(path: string, method: string, body: unknown) {
  if (!['POST', 'PATCH'].includes(method) || !/^\/cases\/[^/]+\/(files\/(compose-office|compose-quote|folders\/(rename|move)|[^/]+\/(rename|move|oo-export-pdf))|finance\/completion-statement)$/.test(path)) return null
  const bytes = new TextEncoder().encode(JSON.stringify([method, path, body ?? null]))
  // WebCrypto hashing requires HTTPS; LAN HTTP still supports getRandomValues.
  const hash = crypto.subtle
    ? Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
    : bytes.reduce((value, byte) => BigInt.asUintN(64, (value ^ BigInt(byte)) * 1099511628211n), 14695981039346656037n).toString(16)
  const storageKey = `canary.document-operation.${hash}`
  let key = pending.get(storageKey)
  try { key = key ?? sessionStorage.getItem(storageKey) ?? undefined } catch { /* Memory remains available. */ }
  if (!key) {
    const random = crypto.getRandomValues(new Uint8Array(16))
    random[6] = (random[6] & 15) | 64
    random[8] = (random[8] & 63) | 128
    const hex = Array.from(random, b => b.toString(16).padStart(2, '0')).join('')
    key = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`
  }
  pending.set(storageKey, key)
  try { sessionStorage.setItem(storageKey, key) } catch { /* Do not prevent a request if storage is unavailable. */ }
  return { key, complete(result: unknown) {
    // A proxy's unexpected success page is not a confirmed operation response.
    if (!result || typeof result !== 'object') return
    if (!('id' in result) && !('file_id' in result) && !('new_folder_path' in result)) return
    if (pending.get(storageKey) === key) pending.delete(storageKey)
    try { if (sessionStorage.getItem(storageKey) === key) sessionStorage.removeItem(storageKey) } catch { /* Optional persistence. */ }
  } }
}
const pending = new Map<string, string>()
