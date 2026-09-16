import { apiUrl, applyAuthHeaders } from '../api'
import type { FeeEarnerPick } from './types'

export function formatMoneyPence(p: number): string {
  const neg = p < 0
  const a = Math.abs(p)
  const s = (a / 100).toFixed(2)
  return `${neg ? '-' : ''}£${s}`
}

export function defaultPeriodEndDate(): string {
  const d = new Date()
  d.setDate(0)
  return d.toISOString().slice(0, 10)
}

export function parsePoundsToPence(input: string): number | null {
  const pounds = parseFloat(input.replace(/,/g, '').trim())
  if (!Number.isFinite(pounds)) return null
  return Math.round(pounds * 100)
}

export function penceToPoundsInput(pence: number): string {
  return (pence / 100).toFixed(2)
}

export function activityRangeForPeriodEnd(periodEnd: string): { from: string; to: string } {
  if (!periodEnd.trim()) return { from: '', to: '' }
  const d = new Date(`${periodEnd.trim()}T12:00:00`)
  if (Number.isNaN(d.getTime())) return { from: '', to: '' }
  const from = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
  return { from, to: periodEnd.trim() }
}

export async function downloadReportXlsx(path: string, body: unknown, token: string, downloadFilename: string) {
  const headers = new Headers()
  applyAuthHeaders(headers, token.trim())
  headers.set('Content-Type', 'application/json')
  const res = await fetch(apiUrl(`${path}?format=xlsx`), { method: 'POST', headers, body: JSON.stringify(body) })
  if (!res.ok) {
    const raw = await res.json().catch(() => ({}))
    const msg = typeof (raw as { detail?: unknown }).detail === 'string' ? (raw as { detail: string }).detail : `Export failed (${res.status})`
    throw new Error(msg)
  }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = downloadFilename
  a.click()
  URL.revokeObjectURL(a.href)
}

export function feeEarnerSummary(selected: Set<string>, feeEarners: FeeEarnerPick[], lockedSingle: boolean): string {
  if (lockedSingle && feeEarners.length === 1) {
    const u = feeEarners[0]
    return u ? `${u.display_name}` : '—'
  }
  const n = selected.size
  if (n === 0) return 'None selected'
  if (n === feeEarners.length && feeEarners.length > 0) return `All (${n})`
  if (n === 1) {
    const id = Array.from(selected)[0]
    const u = feeEarners.find((x) => x.id === id)
    return u ? u.display_name : '1 selected'
  }
  return `${n} selected`
}

export function formatHoursFromMinutes(m: number): string {
  return (m / 60).toFixed(1)
}

export function timeStatusLabel(status: string): string {
  if (status === 'written_off') return 'Written off'
  if (status === 'billed') return 'Billed'
  return 'Unbilled'
}

export function formatLedgerLegs(client?: string | null, office?: string | null): string {
  const parts: string[] = []
  if (client) parts.push(`client ${client}`)
  if (office) parts.push(`office ${office}`)
  return parts.join(' / ') || '—'
}

export function dateRangeSummary(from: string, to: string, emptyLabel = 'All dates'): string {
  if (!from.trim() && !to.trim()) return emptyLabel
  const a = from.trim() || '…'
  const b = to.trim() || '…'
  return `${a} → ${b}`
}
