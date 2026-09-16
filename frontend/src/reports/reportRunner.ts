import { apiFetch, type ApiError } from '../api'
import { downloadReportXlsx } from './utils'

export type ReportRunControls = {
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  setErr: (v: string | null) => void
  setOpenFilterId: (v: string | null) => void
  requireFeeEarners: () => boolean
}

export async function runReportJson<T>(
  controls: ReportRunControls,
  path: string,
  body: object,
  setPreview: (data: T | null) => void,
) {
  if (!controls.requireFeeEarners()) return
  controls.setBusy(true)
  controls.setErr(null)
  setPreview(null)
  controls.setOpenFilterId(null)
  try {
    const data = await apiFetch<T>(`${path}?format=json`, {
      token: controls.token,
      method: 'POST',
      json: body,
    })
    setPreview(data)
  } catch (e) {
    controls.setErr((e as ApiError)?.message ?? 'Report failed')
  } finally {
    controls.setBusy(false)
  }
}

export async function runReportXlsx(controls: ReportRunControls, path: string, body: object, filename: string) {
  if (!controls.requireFeeEarners()) return
  controls.setBusy(true)
  controls.setErr(null)
  controls.setOpenFilterId(null)
  try {
    await downloadReportXlsx(path, body, controls.token, filename)
  } catch (e) {
    controls.setErr((e as Error)?.message ?? 'Export failed')
  } finally {
    controls.setBusy(false)
  }
}
