import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from './api'
import { useDialogs } from './DialogProvider'
import type { ApiError } from './api'

export type AdminDeployStatusOut = {
  configured: boolean
  compose_update_enabled?: boolean
  github_actions_configured?: boolean
  owner?: string | null
  repo?: string | null
  workflow?: string | null
  default_ref?: string | null
}

export function AdminDeploy({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [status, setStatus] = useState<AdminDeployStatusOut | null>(null)
  const [ref, setRef] = useState('')
  const [environment, setEnvironment] = useState('production')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  const load = useCallback(async () => {
    setErr(null)
    setOk(null)
    try {
      const s = await apiFetch<AdminDeployStatusOut>('/admin/deploy/status', { token })
      setStatus(s)
      setRef((prev) => (prev.trim() !== '' ? prev : (s.default_ref ?? 'main').trim()))
    } catch (e) {
      setStatus(null)
      setErr((e as ApiError).message ?? 'Failed to load deploy status')
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  async function triggerCompose() {
    const confirmed = await askConfirm({
      title: 'Update via Docker Compose',
      message:
        'This runs docker compose build --pull and up -d on the server using the mounted project directory and Docker socket. Continue?',
      danger: true,
      confirmLabel: 'Run Compose update',
    })
    if (!confirmed) return
    setBusy(true)
    setErr(null)
    setOk(null)
    try {
      const out = await apiFetch<{ ok: boolean; message: string }>('/admin/deploy/trigger', {
        token,
        method: 'POST',
        json: { method: 'compose' },
      })
      setOk(out.message ?? 'Done.')
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Compose update failed')
    } finally {
      setBusy(false)
    }
  }

  async function triggerGithub() {
    const confirmed = await askConfirm({
      title: 'Run deployment',
      message:
        'This requests a GitHub Actions workflow on the repository. A self-hosted runner on your server must execute Docker Compose. Continue?',
      danger: true,
      confirmLabel: 'Request deploy',
    })
    if (!confirmed) return
    setBusy(true)
    setErr(null)
    setOk(null)
    try {
      const out = await apiFetch<{ ok: boolean; message: string }>('/admin/deploy/trigger', {
        token,
        method: 'POST',
        json: {
          method: 'github',
          ref: ref.trim() || null,
          environment: environment.trim() || null,
        },
      })
      setOk(out.message ?? 'Requested.')
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Deploy request failed')
    } finally {
      setBusy(false)
    }
  }

  const composeOn = Boolean(status?.compose_update_enabled)
  const ghOn = Boolean(status?.github_actions_configured)

  return (
    <div className="stack" style={{ maxWidth: 560 }}>
      {err ? <div className="error">{err}</div> : null}
      {ok ? <div className="muted">{ok}</div> : null}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Update this server (Docker Compose)</h3>
        <p className="muted" style={{ lineHeight: 1.55 }}>
          Recommended for self-hosting: administrators run Compose on the host without any GitHub token. Requires{' '}
          <code>CANARY_COMPOSE_UPDATE_ENABLED</code>, a mounted Docker socket, and the compose project directory (see{' '}
          <code>.env.example</code>). Granting Docker socket access is powerful — restrict who has Admin.
        </p>
        {composeOn ? (
          <p className="muted" style={{ marginTop: 12 }}>
            Compose-based updates are <strong>enabled</strong> on this server.
          </p>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            Compose-based updates are <strong>not configured</strong>.
          </p>
        )}
        <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <button type="button" className="btn primary" disabled={busy || !composeOn} onClick={() => void triggerCompose()}>
            {busy ? 'Working…' : 'Run Compose update'}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Deploy via GitHub Actions</h3>
        <p className="muted" style={{ lineHeight: 1.55 }}>
          Optional: trigger <code>deploy-canary.yml</code> with <code>CANARY_GITHUB_DEPLOY_*</code> and a self-hosted runner.
          If both Compose and GitHub are configured, the post-login “Update now” button uses Compose first.
        </p>

        {ghOn ? (
          <ul className="muted" style={{ marginTop: 12, lineHeight: 1.6, fontSize: '0.95em' }}>
            <li>
              Repository:{' '}
              <strong>
                {status?.owner}/{status?.repo}
              </strong>
            </li>
            <li>
              Workflow file: <strong>{status?.workflow}</strong>
            </li>
            <li>
              Default branch/ref: <strong>{status?.default_ref}</strong>
            </li>
          </ul>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            GitHub Actions deploy is <strong>not configured</strong> on this server.
          </p>
        )}

        <div className="stack" style={{ marginTop: 16, gap: 12 }}>
          <label className="field">
            <span>Git ref (branch or tag)</span>
            <input
              value={ref}
              onChange={(e) => setRef(e.target.value)}
              disabled={busy || !ghOn}
              placeholder="main"
              autoComplete="off"
            />
          </label>
          <label className="field">
            <span>Environment label</span>
            <input
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              disabled={busy || !ghOn}
              placeholder="production"
              autoComplete="off"
            />
            <span className="muted" style={{ fontSize: '0.85em' }}>
              Passed to the workflow as an input (for logs / concurrency); does not select Docker Compose profile.
            </span>
          </label>
        </div>

        <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <button type="button" className="btn primary" disabled={busy || !ghOn} onClick={() => void triggerGithub()}>
            {busy ? 'Requesting…' : 'Request GitHub deploy'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
            Reload
          </button>
        </div>
      </div>

      {!status?.configured ? (
        <p className="muted" style={{ marginTop: 12 }}>
          Neither update path is configured — set Compose env vars and mounts and/or <code>CANARY_GITHUB_DEPLOY_*</code>.
        </p>
      ) : null}
    </div>
  )
}
