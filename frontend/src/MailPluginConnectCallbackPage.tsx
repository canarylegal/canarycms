import { useEffect, useMemo } from 'react'
import { AppLogo } from './AppLogo'

const CLIENT_LABEL = {
  thunderbird: 'Thunderbird',
  outlook: 'Outlook',
} as const

type MailPluginClient = keyof typeof CLIENT_LABEL

function parseCallbackParams(): { client: MailPluginClient; state: string; code: string } | { error: string } {
  const params = new URLSearchParams(window.location.hash.slice(1) || window.location.search)
  const client = params.get('client')?.trim().toLowerCase()
  const state = params.get('state')?.trim() ?? ''
  const code = params.get('code')?.trim() ?? ''
  const error = params.get('error')?.trim() ?? ''
  if (error) {
    return { error }
  }
  if (client !== 'thunderbird' && client !== 'outlook') {
    return { error: 'Missing or invalid client parameter.' }
  }
  if (!state) {
    return { error: 'Missing state parameter.' }
  }
  if (client === 'thunderbird' && !/^[A-Za-z0-9_-]{32,256}$/.test(code)) return { error: 'Missing or invalid authorization code. Connect again from Thunderbird.' }
  return { client, state, code }
}

export default function MailPluginConnectCallbackPage() {
  const params = useMemo(() => parseCallbackParams(), [])
  useEffect(() => { window.history.replaceState(null, '', window.location.pathname) }, [])

  if ('error' in params) {
    return (
      <div className="loginScreen">
        <div className="loginBrandRow">
          <AppLogo />
        </div>
        <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 20 }}>Connection failed</h2>
          <div className="error">{params.error}</div>
        </div>
      </div>
    )
  }

  const clientLabel = CLIENT_LABEL[params.client]
  const thunderbird = params.client === 'thunderbird'
  const handoff = 'ext+canary:auth?' + new URLSearchParams({
    origin: window.location.origin, state: params.state, code: params.code,
  }).toString()

  return (
    <div className="loginScreen">
      <div className="loginBrandRow">
        <AppLogo />
      </div>
      <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
        <h2 style={{ margin: '0 0 8px', fontSize: 20 }}>{thunderbird ? 'Finish connecting Thunderbird' : `${clientLabel} connected`}</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          {thunderbird ? 'Authorization succeeded. Open Thunderbird to finish connecting.' :
            `Authorization succeeded. Return to ${clientLabel} — the add-in should finish connecting automatically. You can close this browser tab.`}
        </p>
        {thunderbird ? <a className="btn primary" href={handoff} rel="noreferrer">Open Thunderbird</a> : null}
      </div>
    </div>
  )
}
