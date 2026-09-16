import { useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import type { FirmSettingsOut } from '../types'

type Props = {
  token: string
  firmSettings: FirmSettingsOut | null
  onReload: () => Promise<void>
  onFirmSettings: (next: FirmSettingsOut) => void
  onError: (message: string | null) => void
}

export function AdminSignaturePanel({
  token,
  firmSettings,
  onReload,
  onFirmSettings,
  onError,
}: Props) {
  const [sigBusy, setSigBusy] = useState(false)
  const [sigFileKey, setSigFileKey] = useState(0)

  async function patchDefaultSignatureScale(scale: number) {
    if (!firmSettings) return
    setSigBusy(true)
    onError(null)
    try {
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: { default_signature_scale: scale },
      })
      onFirmSettings(body)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Could not save signature scale')
    } finally {
      setSigBusy(false)
    }
  }

  async function uploadDefaultSignatureFile(f: File) {
    setSigBusy(true)
    onError(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings/default-signature', {
        token,
        method: 'POST',
        body: fd,
      })
      onFirmSettings(body)
      await onReload()
      setSigFileKey((k) => k + 1)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Signature upload failed')
    } finally {
      setSigBusy(false)
    }
  }

  async function clearDefaultSignatureFile() {
    setSigBusy(true)
    onError(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings/default-signature', { token, method: 'DELETE' })
      await onReload()
      setSigFileKey((k) => k + 1)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Could not remove signature image')
    } finally {
      setSigBusy(false)
    }
  }

  return (
    <div className="card" style={{ padding: 12, marginBottom: 16 }}>
      <h4 style={{ marginTop: 0 }}>Default signature</h4>
      <div className="muted" style={{ marginBottom: 12 }}>
        Upload a firm-wide default e-signature for merge code{' '}
        <code>[FEE_EARNER_SIGNATURE]</code>. Used when the fee earner has not uploaded their own signature in user
        settings. Individual users can override this with their own signature image.
      </div>
      {firmSettings ? (
        <div className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <label className="muted" style={{ minWidth: 120 }}>
              Size in letters
            </label>
            <input
              type="range"
              min={1}
              max={10}
              value={firmSettings.default_signature_scale ?? 7}
              disabled={sigBusy}
              onChange={(ev) => void patchDefaultSignatureScale(Number(ev.target.value))}
            />
            <span style={{ minWidth: 88, textAlign: 'right' }}>
              {firmSettings.default_signature_scale ?? 7} / 10
            </span>
          </div>
          <div className="muted">
            About{' '}
            {(((2 * (firmSettings.default_signature_scale ?? 7)) / 7).toFixed(2))} inches wide in composed documents
          </div>
          <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <label className="btn" style={{ cursor: sigBusy ? 'not-allowed' : 'pointer' }}>
              Upload signature…
              <input
                key={sigFileKey}
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"
                disabled={sigBusy}
                style={{ display: 'none' }}
                onChange={(ev) => {
                  const f = ev.target.files?.[0]
                  ev.target.value = ''
                  if (f) void uploadDefaultSignatureFile(f)
                }}
              />
            </label>
            <span className="muted">
              {firmSettings.default_signature_configured
                ? `Current file: ${firmSettings.default_signature_original_filename ?? 'signature image'}`
                : 'No default signature uploaded yet.'}
            </span>
            {firmSettings.default_signature_configured ? (
              <button
                type="button"
                className="btn danger"
                disabled={sigBusy}
                onClick={() => void clearDefaultSignatureFile()}
              >
                Remove signature
              </button>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="muted">Loading default signature settings…</div>
      )}
    </div>
  )
}
