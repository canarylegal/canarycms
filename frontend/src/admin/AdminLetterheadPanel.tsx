import { useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import { openOnlyOfficeFirmLetterheadEditor } from '../onlyofficeEditorWindow'
import type { FirmSettingsOut, LetterheadStyle } from '../types'

type Props = {
  token: string
  firmSettings: FirmSettingsOut | null
  onReload: () => Promise<void>
  onFirmSettings: (next: FirmSettingsOut) => void
  onError: (message: string | null) => void
}

export function AdminLetterheadPanel({
  token,
  firmSettings,
  onReload,
  onFirmSettings,
  onError,
}: Props) {
  const [lhBusy, setLhBusy] = useState(false)
  const [lhFileKey, setLhFileKey] = useState(0)
  const [qlhBusy, setQlhBusy] = useState(false)
  const [qlhFileKey, setQlhFileKey] = useState(0)

  async function patchLetterheadStyle(next: LetterheadStyle) {
    setLhBusy(true)
    onError(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: { letterhead_style: next },
      })
      await onReload()
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Could not update letterhead mode')
    } finally {
      setLhBusy(false)
    }
  }

  async function uploadLetterheadFile(f: File) {
    setLhBusy(true)
    onError(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings/letterhead', {
        token,
        method: 'POST',
        body: fd,
      })
      onFirmSettings(body)
      await onReload()
      setLhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      onError((e2 as Error)?.message ?? 'Letterhead upload failed')
    } finally {
      setLhBusy(false)
    }
  }

  async function clearLetterheadFile() {
    setLhBusy(true)
    onError(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings/letterhead', { token, method: 'DELETE' })
      await onReload()
      setLhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Could not remove letterhead file')
    } finally {
      setLhBusy(false)
    }
  }

  async function patchQuoteLetterheadStyle(next: LetterheadStyle) {
    setQlhBusy(true)
    onError(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: { quote_letterhead_style: next },
      })
      await onReload()
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Could not update quote letterhead mode')
    } finally {
      setQlhBusy(false)
    }
  }

  async function uploadQuoteLetterheadFile(f: File) {
    setQlhBusy(true)
    onError(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings/quote-letterhead', {
        token,
        method: 'POST',
        body: fd,
      })
      onFirmSettings(body)
      await onReload()
      setQlhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Quote letterhead upload failed')
    } finally {
      setQlhBusy(false)
    }
  }

  async function clearQuoteLetterheadFile() {
    setQlhBusy(true)
    onError(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings/quote-letterhead', { token, method: 'DELETE' })
      await onReload()
      setQlhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Could not remove quote letterhead file')
    } finally {
      setQlhBusy(false)
    }
  }

  return (
    <>
      <div className="card" style={{ padding: 12, marginBottom: 16 }}>
        <h4 style={{ marginTop: 0 }}>Letterhead (Letter precedents only)</h4>
        <div className="muted" style={{ marginBottom: 12 }}>
          <strong>Digital</strong> copies the uploaded .docx <strong>headers and footers</strong> into each{' '}
          <strong>Letter</strong> precedent before merge codes run. Keep logos and firm blocks in the header/footer so the
          letter body can sit on page 1 underneath. <strong>Pre-printed</strong> skips any overlay (headed stationery).
          Embedded logos in the uploaded .docx are copied into each composed letter automatically.
        </div>
        {firmSettings ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: lhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="letterhead-style"
                  checked={firmSettings.letterhead_style === 'preprinted'}
                  disabled={lhBusy}
                  onChange={() => void patchLetterheadStyle('preprinted')}
                />
                Pre-printed
              </label>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: lhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="letterhead-style"
                  checked={firmSettings.letterhead_style === 'digital'}
                  disabled={lhBusy}
                  onChange={() => void patchLetterheadStyle('digital')}
                />
                Digital
              </label>
            </div>
            {firmSettings.letterhead_style === 'digital' ? (
              <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <label className="btn" style={{ cursor: lhBusy ? 'not-allowed' : 'pointer' }}>
                  Browse…
                  <input
                    key={lhFileKey}
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    disabled={lhBusy}
                    style={{ display: 'none' }}
                    onChange={(ev) => {
                      const f = ev.target.files?.[0]
                      ev.target.value = ''
                      if (f) void uploadLetterheadFile(f)
                    }}
                  />
                </label>
                <span className="muted">
                  {firmSettings.letterhead_original_filename
                    ? `Current file: ${firmSettings.letterhead_original_filename}`
                    : 'No .docx uploaded yet.'}
                </span>
                {firmSettings.letterhead_original_filename ? (
                  <>
                    <button
                      type="button"
                      className="btn"
                      disabled={lhBusy}
                      onClick={() => openOnlyOfficeFirmLetterheadEditor('letterhead')}
                    >
                      Edit in OnlyOffice
                    </button>
                    <button type="button" className="btn danger" disabled={lhBusy} onClick={() => void clearLetterheadFile()}>
                      Remove letterhead file
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="muted">Loading letterhead settings…</div>
        )}
      </div>

      <div className="card" style={{ padding: 12, marginBottom: 16 }}>
        <h4 style={{ marginTop: 0 }}>Quote letterhead</h4>
        <div className="muted" style={{ marginBottom: 12 }}>
          The <strong>quote body layout</strong> (text, fee-table merge codes) is edited under <strong>Precedents</strong>{' '}
          as <strong>Quote template</strong> (<code>QUOTE_TEMPLATE</code>). When <strong>Digital</strong> is selected,
          upload a .docx whose <strong>header and footer</strong> contain your logo and firm details — Canary copies those
          onto every new quote document. The letterhead file should not need the fee table; keep that in the quote template
          precedent. Covering letters sent after creating a quote use your normal letter precedents and firm letterhead.
        </div>
        {firmSettings ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: qlhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="quote-letterhead-style"
                  checked={(firmSettings.quote_letterhead_style ?? 'preprinted') === 'preprinted'}
                  disabled={qlhBusy}
                  onChange={() => void patchQuoteLetterheadStyle('preprinted')}
                />
                Pre-printed
              </label>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: qlhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="quote-letterhead-style"
                  checked={(firmSettings.quote_letterhead_style ?? 'preprinted') === 'digital'}
                  disabled={qlhBusy}
                  onChange={() => void patchQuoteLetterheadStyle('digital')}
                />
                Digital
              </label>
            </div>
            {(firmSettings.quote_letterhead_style ?? 'preprinted') === 'digital' ? (
              <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <label className="btn" style={{ cursor: qlhBusy ? 'not-allowed' : 'pointer' }}>
                  Browse…
                  <input
                    key={qlhFileKey}
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    disabled={qlhBusy}
                    style={{ display: 'none' }}
                    onChange={(ev) => {
                      const f = ev.target.files?.[0]
                      ev.target.value = ''
                      if (f) void uploadQuoteLetterheadFile(f)
                    }}
                  />
                </label>
                <span className="muted">
                  {firmSettings.quote_letterhead_original_filename
                    ? `Current file: ${firmSettings.quote_letterhead_original_filename}`
                    : 'No .docx uploaded yet.'}
                </span>
                {firmSettings.quote_letterhead_original_filename ? (
                  <>
                    <button
                      type="button"
                      className="btn"
                      disabled={qlhBusy}
                      onClick={() => openOnlyOfficeFirmLetterheadEditor('quote_letterhead')}
                    >
                      Edit in OnlyOffice
                    </button>
                    <button type="button" className="btn danger" disabled={qlhBusy} onClick={() => void clearQuoteLetterheadFile()}>
                      Remove letterhead file
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="muted">Loading quote letterhead settings…</div>
        )}
      </div>
    </>
  )
}
