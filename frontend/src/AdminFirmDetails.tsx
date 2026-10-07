import { useEffect, useMemo, useState } from 'react'
import { apiFetch, apiUrl } from './api'
import type { ApiError } from './api'
import type { FirmSettingsOut } from './types'
import { FirmModuleAdminPageSlot } from './firm/FirmModuleStubSlots'
import {
  DEFAULT_PORTAL_BACKGROUND,
  DEFAULT_PORTAL_FONT_COLOR,
  normalizePortalBackgroundColor,
  normalizePortalFontColor,
  portalBackgroundContrastOk,
} from './portal/portalBackground'

export function AdminFirmDetails({ token }: { token: string }) {
  const [row, setRow] = useState<FirmSettingsOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [logoBusy, setLogoBusy] = useState(false)
  const [logoFileKey, setLogoFileKey] = useState(0)
  const [bgBusy, setBgBusy] = useState(false)
  const [bgFileKey, setBgFileKey] = useState(0)
  const [err, setErr] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const [tradingName, setTradingName] = useState('')
  const [registeredName, setRegisteredName] = useState('')
  const [addr1, setAddr1] = useState('')
  const [addr2, setAddr2] = useState('')
  const [town, setTown] = useState('')
  const [county, setCounty] = useState('')
  const [postcode, setPostcode] = useState('')
  const [clientBankName, setClientBankName] = useState('')
  const [clientBankSort, setClientBankSort] = useState('')
  const [clientBankAccountNumber, setClientBankAccountNumber] = useState('')
  const [clientBankLast4, setClientBankLast4] = useState('')
  /** Draft hex text (may be partial while typing). Empty = product default. */
  const [portalBgHex, setPortalBgHex] = useState('')
  const [portalFontHex, setPortalFontHex] = useState('')
  const [portalBgOnSignedIn, setPortalBgOnSignedIn] = useState(true)
  const [portalLogoEnabled, setPortalLogoEnabled] = useState(true)
  const [clientPortalEnabled, setClientPortalEnabled] = useState(true)
  const [canarySignEnabled, setCanarySignEnabled] = useState(true)
  const [brandSupportInbox, setBrandSupportInbox] = useState('')
  const [brandPoweredByLabel, setBrandPoweredByLabel] = useState('')
  const [brandPoweredByUrl, setBrandPoweredByUrl] = useState('')
  const [brandPoweredByHide, setBrandPoweredByHide] = useState(false)

  const portalBgNormalized = useMemo(() => normalizePortalBackgroundColor(portalBgHex), [portalBgHex])
  const portalBgPreview = portalBgNormalized ?? DEFAULT_PORTAL_BACKGROUND
  const portalFontNormalized = useMemo(() => normalizePortalFontColor(portalFontHex), [portalFontHex])
  const portalFontPreview = portalFontNormalized ?? DEFAULT_PORTAL_FONT_COLOR
  const portalBgContrastOk = useMemo(
    () => portalBackgroundContrastOk(portalBgPreview, portalFontPreview),
    [portalBgPreview, portalFontPreview],
  )
  const portalBgHexInvalid = Boolean(portalBgHex.trim()) && portalBgNormalized == null
  const portalFontHexInvalid = Boolean(portalFontHex.trim()) && portalFontNormalized == null

  async function load() {
    setErr(null)
    setSaved(false)
    try {
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings', { token })
      setRow(data)
      setTradingName(data.trading_name ?? '')
      setRegisteredName(data.registered_company_name ?? '')
      setAddr1(data.addr_line1 ?? '')
      setAddr2(data.addr_line2 ?? '')
      setTown(data.town_city ?? '')
      setCounty(data.county ?? '')
      setPostcode(data.postcode ?? '')
      setClientBankName(data.client_bank_account_name ?? '')
      setClientBankSort(data.client_bank_sort_code ?? '')
      setClientBankAccountNumber(data.client_bank_account_number ?? '')
      setClientBankLast4(data.client_bank_account_number_last4 ?? '')
      setPortalBgHex((data.portal_background_color || '').trim())
      setPortalFontHex((data.portal_font_color || '').trim())
      setPortalBgOnSignedIn(data.portal_background_on_signed_in !== false)
      setPortalLogoEnabled(data.portal_logo_enabled !== false)
      setClientPortalEnabled(data.client_portal_enabled !== false)
      setCanarySignEnabled(data.canary_sign_enabled !== false)
      setBrandSupportInbox((data.brand_support_inbox || '').trim())
      setBrandPoweredByLabel((data.brand_powered_by_label || '').trim())
      setBrandPoweredByUrl((data.brand_powered_by_url || '').trim())
      setBrandPoweredByHide(Boolean(data.brand_powered_by_hide))
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load firm details')
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  async function save() {
    setBusy(true)
    setErr(null)
    setSaved(false)
    try {
      if (portalBgHexInvalid) {
        setErr('Enter a valid hex colour such as #1E293B, or clear the field for the default.')
        setBusy(false)
        return
      }
      if (portalFontHexInvalid) {
        setErr('Enter a valid font hex colour such as #F8FAFC, or clear the field for the default.')
        setBusy(false)
        return
      }
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: {
          trading_name: tradingName.trim(),
          registered_company_name: registeredName.trim() || null,
          addr_line1: addr1.trim() || null,
          addr_line2: addr2.trim() || null,
          town_city: town.trim() || null,
          county: county.trim() || null,
          postcode: postcode.trim() || null,
          client_bank_account_name: clientBankName.trim() || null,
          client_bank_sort_code: clientBankSort.trim() || null,
          client_bank_account_number: clientBankAccountNumber.trim() || null,
          client_bank_account_number_last4: clientBankLast4.trim() || null,
          // Empty string clears to product default on the server.
          portal_background_color: portalBgNormalized ?? '',
          portal_font_color: portalFontNormalized ?? '',
          portal_background_on_signed_in: portalBgOnSignedIn,
          portal_logo_enabled: portalLogoEnabled,
          client_portal_enabled: clientPortalEnabled,
          canary_sign_enabled: canarySignEnabled,
          brand_support_inbox: brandSupportInbox.trim(),
          brand_powered_by_label: brandPoweredByLabel.trim(),
          brand_powered_by_url: brandPoweredByUrl.trim(),
          brand_powered_by_hide: brandPoweredByHide,
        },
      })
      setRow(data)
      setPortalBgHex((data.portal_background_color || '').trim())
      setPortalFontHex((data.portal_font_color || '').trim())
      setPortalBgOnSignedIn(data.portal_background_on_signed_in !== false)
      setPortalLogoEnabled(data.portal_logo_enabled !== false)
      setClientPortalEnabled(data.client_portal_enabled !== false)
      setCanarySignEnabled(data.canary_sign_enabled !== false)
      setBrandSupportInbox((data.brand_support_inbox || '').trim())
      setBrandPoweredByLabel((data.brand_powered_by_label || '').trim())
      setBrandPoweredByUrl((data.brand_powered_by_url || '').trim())
      setBrandPoweredByHide(Boolean(data.brand_powered_by_hide))
      setSaved(true)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function uploadPortalLogo(file: File) {
    setLogoBusy(true)
    setErr(null)
    setSaved(false)
    try {
      const fd = new FormData()
      fd.append('upload', file)
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings/portal-logo', {
        token,
        method: 'POST',
        body: fd,
      })
      setRow(data)
      setLogoFileKey((k) => k + 1)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Portal logo upload failed')
    } finally {
      setLogoBusy(false)
    }
  }

  async function removePortalLogo() {
    setLogoBusy(true)
    setErr(null)
    setSaved(false)
    try {
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings/portal-logo', {
        token,
        method: 'DELETE',
      })
      setRow(data)
      setLogoFileKey((k) => k + 1)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not remove portal logo')
    } finally {
      setLogoBusy(false)
    }
  }

  async function uploadPortalBackground(file: File) {
    setBgBusy(true)
    setErr(null)
    setSaved(false)
    try {
      const fd = new FormData()
      fd.append('upload', file)
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings/portal-background', {
        token,
        method: 'POST',
        body: fd,
      })
      setRow(data)
      setBgFileKey((k) => k + 1)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Portal background upload failed')
    } finally {
      setBgBusy(false)
    }
  }

  async function removePortalBackground() {
    setBgBusy(true)
    setErr(null)
    setSaved(false)
    try {
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings/portal-background', {
        token,
        method: 'DELETE',
      })
      setRow(data)
      setBgFileKey((k) => k + 1)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not remove portal background')
    } finally {
      setBgBusy(false)
    }
  }

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Firm details</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Reload
        </button>
      </div>
      <div className="muted" style={{ marginBottom: 8 }}>
        Used as precedent merge codes (<code>[FIRM_*]</code>) and shown when composing letters. Letterhead layout for{' '}
        <strong>Letter</strong> precedents is configured under <strong>Admin → Precedents</strong>.
      </div>
      {err ? <div className="error">{err}</div> : null}
      {saved ? <div className="muted">Saved.</div> : null}

      <div className="card" style={{ padding: 16 }}>
        {!row ? (
          <div className="muted">Loading…</div>
        ) : (
          <div className="stack" style={{ gap: 12 }}>
            <label className="field">
              <span>Firm trading name</span>
              <input value={tradingName} onChange={(e) => setTradingName(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Registered company name (optional)</span>
              <input value={registeredName} onChange={(e) => setRegisteredName(e.target.value)} disabled={busy} />
            </label>
            <div style={{ fontWeight: 600, marginTop: 8 }}>Optional products</div>
            <label className="row" style={{ gap: 10, alignItems: 'flex-start', cursor: busy ? 'default' : 'pointer' }}>
              <input
                type="checkbox"
                checked={clientPortalEnabled}
                disabled={busy}
                onChange={(e) => setClientPortalEnabled(e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                <span style={{ fontWeight: 600 }}>Client portal product</span>
                <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                  Untick to turn the portal off firm-wide. Matter toggles and type defaults are ignored while this is
                  off.
                </div>
              </span>
            </label>
            <label className="row" style={{ gap: 10, alignItems: 'flex-start', cursor: busy ? 'default' : 'pointer' }}>
              <input
                type="checkbox"
                checked={canarySignEnabled}
                disabled={busy}
                onChange={(e) => setCanarySignEnabled(e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                <span style={{ fontWeight: 600 }}>Canary Sign</span>
                <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                  Independent of the portal. Untick if the firm uses another e-sign product or wet ink only.
                </div>
              </span>
            </label>

            <div style={{ fontWeight: 600, marginTop: 8 }}>Client portal</div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
              Shown at the top of the client portal as <strong>{tradingName.trim() || 'Firm name'} Portal</strong>.
              Use a horizontal logo on a transparent background (PNG, JPEG, or WebP, max 2 MB).
            </div>
            {row.portal_logo_configured ? (
              <div className="stack" style={{ gap: 8 }}>
                <img
                  key={logoFileKey}
                  src={`${apiUrl('/portal/logo')}?v=${logoFileKey}`}
                  alt="Current portal logo preview"
                  style={{ maxWidth: 240, maxHeight: 72, objectFit: 'contain' }}
                />
                <div className="muted" style={{ fontSize: 13 }}>
                  {row.portal_logo_original_filename ?? 'Logo uploaded'}
                </div>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  <label className="btn" style={{ cursor: logoBusy ? 'wait' : 'pointer' }}>
                    Replace logo
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                      hidden
                      disabled={logoBusy || busy}
                      onChange={(e) => {
                        const f = e.target.files?.[0]
                        e.target.value = ''
                        if (f) void uploadPortalLogo(f)
                      }}
                    />
                  </label>
                  <button type="button" className="btn" disabled={logoBusy || busy} onClick={() => void removePortalLogo()}>
                    Remove logo
                  </button>
                </div>
              </div>
            ) : (
              <label className="btn" style={{ cursor: logoBusy ? 'wait' : 'pointer', alignSelf: 'flex-start' }}>
                Upload portal logo
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                  hidden
                  disabled={logoBusy || busy}
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    e.target.value = ''
                    if (f) void uploadPortalLogo(f)
                  }}
                />
              </label>
            )}
            <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                checked={portalLogoEnabled}
                disabled={busy || !row.portal_logo_configured}
                onChange={(e) => setPortalLogoEnabled(e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                <span style={{ fontWeight: 600 }}>Show firm logo on the client portal</span>
                <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                  Untick to hide the logo on login and signed-in views. The uploaded file is kept so you can turn it
                  back on later.
                  {!row.portal_logo_configured ? ' Upload a logo first.' : ''}
                </div>
              </span>
            </label>

            <div style={{ fontWeight: 600, marginTop: 4 }}>Portal background image</div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
              Optional full-bleed image (PNG, JPEG, or WebP, max 5 MB). Used only when no solid background colour is
              set — a chosen colour always wins over the image.
            </div>
            {row.portal_background_configured ? (
              <div className="stack" style={{ gap: 8 }}>
                <img
                  key={bgFileKey}
                  src={`${apiUrl('/portal/background')}?v=${bgFileKey}`}
                  alt="Current portal background preview"
                  style={{
                    width: '100%',
                    maxHeight: 140,
                    objectFit: 'cover',
                    borderRadius: 10,
                    border: '1px solid rgba(15,23,42,0.12)',
                  }}
                />
                <div className="muted" style={{ fontSize: 13 }}>
                  {row.portal_background_original_filename ?? 'Background uploaded'}
                </div>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  <label className="btn" style={{ cursor: bgBusy ? 'wait' : 'pointer' }}>
                    Replace background
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                      hidden
                      disabled={bgBusy || busy}
                      onChange={(e) => {
                        const f = e.target.files?.[0]
                        e.target.value = ''
                        if (f) void uploadPortalBackground(f)
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn"
                    disabled={bgBusy || busy}
                    onClick={() => void removePortalBackground()}
                  >
                    Remove background
                  </button>
                </div>
              </div>
            ) : (
              <label className="btn" style={{ cursor: bgBusy ? 'wait' : 'pointer', alignSelf: 'flex-start' }}>
                Upload portal background
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                  hidden
                  disabled={bgBusy || busy}
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    e.target.value = ''
                    if (f) void uploadPortalBackground(f)
                  }}
                />
              </label>
            )}
            <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                checked={portalBgOnSignedIn}
                disabled={busy || !row.portal_background_configured}
                onChange={(e) => setPortalBgOnSignedIn(e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                <span style={{ fontWeight: 600 }}>Also show this background after login</span>
                <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                  When ticked, the login background image (and any colour / font settings) also apply on the signed-in
                  portal. When unticked, only the login screen uses them — after sign-in the portal uses Canary’s
                  default chrome.
                  {!row.portal_background_configured ? ' Upload a background image first.' : ''}
                </div>
              </span>
            </label>

            <div style={{ fontWeight: 600, marginTop: 4 }}>Portal background colour</div>
            <div className="muted" style={{ fontSize: 13 }}>
              Solid page colour behind the client portal only (staff UI is unchanged). Use the colour picker or enter a
              hex code. Leave empty for the Canary default.
            </div>
            <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="field" style={{ margin: 0 }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  Colour
                </span>
                <input
                  type="color"
                  value={portalBgPreview.toLowerCase()}
                  disabled={busy}
                  aria-label="Portal background colour picker"
                  onChange={(e) => setPortalBgHex(e.target.value.toUpperCase())}
                  style={{ width: 48, height: 36, padding: 0, border: '1px solid rgba(15,23,42,0.2)', cursor: 'pointer' }}
                />
              </label>
              <label className="field" style={{ margin: 0, minWidth: 140 }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  Hex
                </span>
                <input
                  value={portalBgHex}
                  onChange={(e) => setPortalBgHex(e.target.value)}
                  disabled={busy}
                  placeholder={DEFAULT_PORTAL_BACKGROUND}
                  spellCheck={false}
                  autoComplete="off"
                  aria-invalid={portalBgHexInvalid}
                />
              </label>
              <button
                type="button"
                className="btn"
                disabled={busy || !portalBgHex.trim()}
                onClick={() => setPortalBgHex('')}
                style={{ alignSelf: 'flex-end' }}
              >
                Use default
              </button>
            </div>
            {portalBgHexInvalid ? (
              <div className="error" style={{ fontSize: 13 }}>
                Enter a valid hex colour such as #1E293B or #ABC.
              </div>
            ) : null}

            <div style={{ fontWeight: 600, marginTop: 4 }}>Portal font colour</div>
            <div className="muted" style={{ fontSize: 13 }}>
              Colour for the portal title, subtitle, sign-out control, and powered-by text on the page background
              (content inside the white card stays dark for readability). Leave empty for the default light ink.
            </div>
            <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="field" style={{ margin: 0 }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  Colour
                </span>
                <input
                  type="color"
                  value={portalFontPreview.toLowerCase()}
                  disabled={busy}
                  aria-label="Portal font colour picker"
                  onChange={(e) => setPortalFontHex(e.target.value.toUpperCase())}
                  style={{ width: 48, height: 36, padding: 0, border: '1px solid rgba(15,23,42,0.2)', cursor: 'pointer' }}
                />
              </label>
              <label className="field" style={{ margin: 0, minWidth: 140 }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  Hex
                </span>
                <input
                  value={portalFontHex}
                  onChange={(e) => setPortalFontHex(e.target.value)}
                  disabled={busy}
                  placeholder={DEFAULT_PORTAL_FONT_COLOR}
                  spellCheck={false}
                  autoComplete="off"
                  aria-invalid={portalFontHexInvalid}
                />
              </label>
              <button
                type="button"
                className="btn"
                disabled={busy || !portalFontHex.trim()}
                onClick={() => setPortalFontHex('')}
                style={{ alignSelf: 'flex-end' }}
              >
                Use default
              </button>
            </div>
            {portalFontHexInvalid ? (
              <div className="error" style={{ fontSize: 13 }}>
                Enter a valid hex colour such as #F8FAFC or #ABC.
              </div>
            ) : null}
            {!portalBgHexInvalid && !portalFontHexInvalid && !portalBgContrastOk ? (
              <div className="muted" style={{ fontSize: 13, color: '#b45309' }}>
                This font colour may be hard to read on the chosen background. Prefer higher contrast, or check the
                preview below.
              </div>
            ) : null}
            <div
              aria-label="Portal background preview"
              style={{
                borderRadius: 12,
                padding: '20px 16px',
                backgroundColor: portalBgPreview,
                backgroundImage: row.portal_background_configured
                  ? `url("${apiUrl('/portal/background')}?v=${bgFileKey}")`
                  : undefined,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                border: '1px solid rgba(15,23,42,0.12)',
              }}
            >
              <div style={{ textAlign: 'center', color: portalFontPreview, fontWeight: 700, fontSize: 18 }}>
                {(tradingName.trim() || 'Firm name') + ' Portal'}
              </div>
              <div
                style={{
                  textAlign: 'center',
                  color: portalFontPreview,
                  opacity: 0.78,
                  fontSize: 13,
                  marginTop: 4,
                }}
              >
                Signed in as Client Name
              </div>
              <div
                style={{
                  marginTop: 14,
                  background: '#fff',
                  borderRadius: 10,
                  padding: '14px 12px',
                  color: '#0f172a',
                  fontSize: 13,
                  boxShadow: '0 8px 24px rgba(15,23,42,0.18)',
                }}
              >
                Preview of the white content card on your chosen background.
              </div>
            </div>

            <div style={{ fontWeight: 600, marginTop: 8 }}>Support &amp; portal attribution</div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
              Overrides for this install. Leave blank to use the deployment defaults
              {row.env_support_inbox ? (
                <>
                  {' '}
                  (<code>{row.env_support_inbox}</code>
                  {row.env_powered_by_hide ? '; powered-by hidden by env' : ''})
                </>
              ) : null}
              . Does not rename the Canary product.
            </div>
            <label className="field">
              <span>Support inbox (staff tickets)</span>
              <input
                value={brandSupportInbox}
                onChange={(e) => setBrandSupportInbox(e.target.value)}
                disabled={busy}
                placeholder={row.env_support_inbox || 'support@example.com'}
                autoComplete="off"
              />
            </label>
            <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                checked={brandPoweredByHide}
                disabled={busy}
                onChange={(e) => setBrandPoweredByHide(e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                <span style={{ fontWeight: 600 }}>Hide “Powered by” on the client portal</span>
                <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                  {row.env_powered_by_hide
                    ? 'Also hidden by deployment env (CANARY_BRAND_POWERED_BY_HIDE).'
                    : 'When unchecked, the footer uses the label/URL below or the deployment default.'}
                </div>
              </span>
            </label>
            <label className="field">
              <span>Powered-by label</span>
              <input
                value={brandPoweredByLabel}
                onChange={(e) => setBrandPoweredByLabel(e.target.value)}
                disabled={busy || brandPoweredByHide}
                placeholder={row.env_powered_by_label || 'Powered by …'}
              />
            </label>
            <label className="field">
              <span>Powered-by URL</span>
              <input
                value={brandPoweredByUrl}
                onChange={(e) => setBrandPoweredByUrl(e.target.value)}
                disabled={busy || brandPoweredByHide}
                placeholder={row.env_powered_by_url || 'https://…'}
              />
            </label>

            <div style={{ fontWeight: 600, marginTop: 8 }}>Firm address</div>
            <label className="field">
              <span>Address line 1</span>
              <input value={addr1} onChange={(e) => setAddr1(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Address line 2</span>
              <input value={addr2} onChange={(e) => setAddr2(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Town / city</span>
              <input value={town} onChange={(e) => setTown(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>County</span>
              <input value={county} onChange={(e) => setCounty(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Postcode</span>
              <input value={postcode} onChange={(e) => setPostcode(e.target.value)} disabled={busy} />
            </label>
            <div style={{ fontWeight: 600, marginTop: 8 }}>Client bank account (for reconcile report)</div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
              Used on the client account reconcile report.
            </div>
            <label className="field">
              <span>Account name</span>
              <input value={clientBankName} onChange={(e) => setClientBankName(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Sort code</span>
              <input value={clientBankSort} onChange={(e) => setClientBankSort(e.target.value)} disabled={busy} placeholder="12-34-56" />
            </label>
            <label className="field">
              <span>Account number</span>
              <input
                value={clientBankAccountNumber}
                onChange={(e) => {
                  const digits = e.target.value.replace(/\D/g, '').slice(0, 20)
                  setClientBankAccountNumber(digits)
                  setClientBankLast4(digits.slice(-4))
                }}
                disabled={busy}
                inputMode="numeric"
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>Account number (last 4 digits, optional override)</span>
              <input
                value={clientBankLast4}
                onChange={(e) => setClientBankLast4(e.target.value.replace(/\D/g, '').slice(0, 4))}
                disabled={busy}
                maxLength={4}
                inputMode="numeric"
              />
            </label>
            <button type="button" className="btn primary" onClick={() => void save()} disabled={busy || portalBgHexInvalid}>
              Save firm details
            </button>
          </div>
        )}
        {/* Phase 4 stub slot — mounts only if firm bundle exports AdminPage */}
        <FirmModuleAdminPageSlot token={token} />
      </div>
    </div>
  )
}
