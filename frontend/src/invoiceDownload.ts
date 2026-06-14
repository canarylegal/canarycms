/** Download helpers for approved invoice .docx documents. */

import { apiUrl, applyAuthHeaders } from './api'

export async function downloadInvoiceDocument(
  caseId: string,
  invoiceId: string,
  token: string,
  downloadFilename: string,
): Promise<void> {
  const headers = new Headers()
  applyAuthHeaders(headers, token.trim())
  const res = await fetch(apiUrl(`/cases/${caseId}/invoices/${invoiceId}/document.docx`), { headers })
  if (!res.ok) {
    const raw = await res.json().catch(() => ({}))
    const msg =
      typeof (raw as { detail?: unknown }).detail === 'string'
        ? (raw as { detail: string }).detail
        : `Download failed (${res.status})`
    throw new Error(msg)
  }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = downloadFilename
  a.click()
  URL.revokeObjectURL(a.href)
}

export function invoiceDownloadFilename(invoiceNumber: string): string {
  const safe = invoiceNumber.replace(/[^\w-]+/g, '-').replace(/^-+|-+$/g, '') || 'invoice'
  return `Invoice ${safe}.docx`
}
