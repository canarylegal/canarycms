import { Component, type ReactNode, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './local-modern.css'
import { applyStoredTheme } from './theme'
import { DialogProvider } from './DialogProvider'
import { NotificationsProvider } from './NotificationsProvider'

applyStoredTheme()
import EditorPage from './EditorPage.tsx'

class AppErrorBoundary extends Component<{ children: ReactNode }, { err: Error | null; refId: string }> {
  state = { err: null as Error | null, refId: '' }

  static getDerivedStateFromError(err: Error) {
    const refId =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID().slice(0, 8).toUpperCase()
        : String(Date.now()).slice(-8)
    return { err, refId }
  }

  componentDidCatch(err: Error, info: { componentStack?: string | null }) {
    console.error('Canary runtime error', this.state.refId, err, info.componentStack)
  }

  render() {
    if (this.state.err) {
      const err = this.state.err
      const isDev = import.meta.env.DEV
      return (
        <div
          style={{
            padding: 24,
            fontFamily: 'system-ui, sans-serif',
            background: 'var(--page-gradient)',
            color: '#0f172a',
            minHeight: '100vh',
          }}
        >
          <h1 style={{ color: '#b91c1c' }}>Something went wrong</h1>
          <p style={{ color: '#64748b', marginBottom: 12 }}>
            Reload Canary to continue. Reference: <code>{this.state.refId || '—'}</code>
          </p>
          <button
            type="button"
            className="btn primary"
            style={{ marginBottom: 16 }}
            onClick={() => window.location.reload()}
          >
            Reload Canary
          </button>
          {isDev ? (
            <div style={{ whiteSpace: 'pre-wrap', color: '#dc2626' }}>
              <p style={{ color: '#64748b', marginBottom: 8 }}>Development details:</p>
              <pre
                style={{
                  margin: '0 0 16px',
                  padding: 12,
                  background: 'rgba(255,255,255,0.92)',
                  color: '#0f172a',
                  borderRadius: 8,
                  fontSize: 14,
                  lineHeight: 1.45,
                }}
              >
                {err.message || String(err)}
              </pre>
              <p style={{ color: '#64748b', marginBottom: 8 }}>Stack:</p>
              {err.stack ?? String(err)}
            </div>
          ) : null}
        </div>
      )
    }
    return this.props.children
  }
}

const el = document.getElementById('root')
if (!el) {
  document.body.innerHTML = '<p style="padding:24px;font-family:sans-serif">Missing #root — index.html is invalid.</p>'
} else {
  const root = createRoot(el)

  const searchParams = new URLSearchParams(window.location.search)
  const ledgerCaseId = searchParams.get('ledger')

  if (
    window.location.pathname === '/portal' ||
    /^\/portal\/q\/[^/]+$/i.test(window.location.pathname) ||
    /^\/portal\/f\/[^/]+$/i.test(window.location.pathname) ||
    /^\/portal\/s\/[^/]+$/i.test(window.location.pathname)
  ) {
    document.documentElement.style.zoom = '1'
    // Client portal must not inherit staff Appearance page-bg / dark mode.
    document.documentElement.classList.remove('dark')
    document.documentElement.style.removeProperty('--page-bg')
    document.documentElement.style.removeProperty('--bg')
    document.documentElement.style.removeProperty('--page-gradient')
    document.documentElement.style.removeProperty('--text-on-page-bg')
    void import('./PortalPage.tsx').then(({ default: PortalPage }) => {
      root.render(<PortalPage />)
    })
  } else if (window.location.pathname === '/connect/mail-plugin/callback') {
    document.documentElement.style.zoom = '1'
    void import('./MailPluginConnectCallbackPage.tsx').then(({ default: MailPluginConnectCallbackPage }) => {
      root.render(
        <StrictMode>
          <AppErrorBoundary>
            <MailPluginConnectCallbackPage />
          </AppErrorBoundary>
        </StrictMode>,
      )
    })
  } else if (window.location.pathname === '/connect/mail-plugin') {
    document.documentElement.style.zoom = '1'
    void import('./MailPluginConnectPage.tsx').then(({ default: MailPluginConnectPage }) => {
      root.render(
        <StrictMode>
          <AppErrorBoundary>
            <MailPluginConnectPage />
          </AppErrorBoundary>
        </StrictMode>,
      )
    })
  } else if (window.location.pathname === '/oo-print') {
    document.documentElement.style.zoom = '1'
    void import('./OnlyOfficePrintPage.tsx').then(({ default: OnlyOfficePrintPage }) => {
      root.render(<OnlyOfficePrintPage />)
    })
  } else if (window.location.pathname.startsWith('/editor/')) {
    // Reset the html { zoom: 1.2 } from index.css — OO DS needs unscaled coordinates
    document.documentElement.style.zoom = '1'
    // No StrictMode: ONLYOFFICE DocEditor is a third-party embed and breaks on double mount.
    root.render(
      <AppErrorBoundary>
        <DialogProvider>
          <EditorPage />
        </DialogProvider>
      </AppErrorBoundary>,
    )
  } else if (ledgerCaseId || searchParams.get('finance')) {
    const financeCaseId = searchParams.get('finance')
    const storedToken = localStorage.getItem('token') ?? ''
    if (!storedToken) {
      root.render(
        <div style={{ padding: 32, fontFamily: 'system-ui, sans-serif', color: '#64748b' }}>
          Please log in to Canary first, then reopen this tab.
        </div>,
      )
    } else if (financeCaseId) {
      void import('./FinancePage.tsx').then(({ FinanceStandalone }) => {
        root.render(
          <StrictMode>
            <AppErrorBoundary>
              <DialogProvider>
                <FinanceStandalone caseId={financeCaseId} token={storedToken} />
              </DialogProvider>
            </AppErrorBoundary>
          </StrictMode>,
        )
      })
    } else {
      void import('./LedgerPage.tsx').then(({ LedgerStandalone }) => {
        root.render(
          <StrictMode>
            <AppErrorBoundary>
              <DialogProvider>
                <LedgerStandalone caseId={ledgerCaseId!} token={storedToken} />
              </DialogProvider>
            </AppErrorBoundary>
          </StrictMode>,
        )
      })
    }
  } else {
    void import('./App.tsx').then(({ default: App }) => {
      root.render(
        <StrictMode>
          <AppErrorBoundary>
            <DialogProvider>
              <NotificationsProvider>
                <App />
              </NotificationsProvider>
            </DialogProvider>
          </AppErrorBoundary>
        </StrictMode>,
      )
    })
  }
}
