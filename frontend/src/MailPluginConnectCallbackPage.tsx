import { useMemo } from 'react'
import { AppLogo } from './AppLogo'

const CLIENT_LABEL = {
  thunderbird: 'Thunderbird',
  outlook: 'Outlook',
} as const

type MailPluginClient = keyof typeof CLIENT_LABEL

function parseCallbackParams(): { client: MailPluginClient; state: string } | { error: string } {
  const params = new URLSearchParams(window.location.search)
  const client = params.get('client')?.trim().toLowerCase()
  const state = params.get('state')?.trim() ?? ''
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
  return { client, state }
}

export default function MailPluginConnectCallbackPage() {
  const params = useMemo(() => parseCallbackParams(), [])

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

  return (
    <div className="loginScreen">
      <div className="loginBrandRow">
        <AppLogo />
      </div>
      <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
        <h2 style={{ margin: '0 0 8px', fontSize: 20 }}>{clientLabel} connected</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Authorization succeeded. Return to {clientLabel} — the add-in should finish connecting automatically. You can
          close this browser tab.
        </p>
      </div>
    </div>
  )
}
