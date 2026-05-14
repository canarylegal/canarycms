import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from './api'
import { postDeployTriggerAndWaitForCompose } from './composeDeployPoll'
import { useDialogs } from './DialogProvider'
import type { ApiError } from './api'
import type { AdminDeployUpdateCheckOut } from './types'

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
  const [updateCheck, setUpdateCheck] = useState<AdminDeployUpdateCheckOut | null>(null)
  const [updateCheckBusy, setUpdateCheckBusy] = useState(false)
  const [updateCheckErr, setUpdateCheckErr] = useState<string | null>(null)
  const [updateCheckAt, setUpdateCheckAt] = useState<Date | null>(null)

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

  const checkForUpdates = useCallback(async () => {
    setUpdateCheckBusy(true)
    setUpdateCheckErr(null)
    try {
      const d = await apiFetch<AdminDeployUpdateCheckOut>('/admin/deploy/update-check', { token })
      setUpdateCheck(d)
      setUpdateCheckAt(new Date())
    } catch (e) {
      setUpdateCheck(null)
      setUpdateCheckErr((e as ApiError).message ?? 'Update check failed')
    } finally {
      setUpdateCheckBusy(false)
    }
  }, [token])

  useEffect(() => {
    void load()
    void checkForUpdates()
  }, [load, checkForUpdates])

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
      const { message } = await postDeployTriggerAndWaitForCompose(token, { method: 'compose' })
      setOk(message)
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
      const { message } = await postDeployTriggerAndWaitForCompose(token, {
        method: 'github',
        ref: ref.trim() || null,
        environment: environment.trim() || null,
      })
      setOk(message)
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
        <h3 style={{ marginTop: 0 }}>Check for updates</h3>
        <p className="muted" style={{ lineHeight: 1.55 }}>
          Compares the running backend image against the tip of the configured GitHub branch. The post-login
          prompt only runs once per session (and is silenced for any version dismissed with “Skip this version”);
          use this button to re-check at any time without logging out.
        </p>

        {updateCheckErr ? <div className="error" style={{ marginBottom: 10 }}>{updateCheckErr}</div> : null}

        {updateCheck ? (
          <ul className="muted" style={{ marginTop: 12, lineHeight: 1.6, fontSize: '0.95em' }}>
            <li>
              Running commit:{' '}
              <strong>
                {updateCheck.build_commit_unknown ? 'unknown' : updateCheck.current_commit_short}
              </strong>
              {updateCheck.build_commit_unknown ? (
                <span> — image was built without the <code>GIT_COMMIT</code> build-arg, so updates cannot be detected.</span>
              ) : null}
            </li>
            {updateCheck.github_repo_configured ? (
              <>
                <li>
                  Remote ref: <strong>{updateCheck.remote_ref || '(default)'}</strong>
                </li>
                <li>
                  Remote tip:{' '}
                  <strong>{updateCheck.remote_commit_short || '—'}</strong>
                </li>
                <li>
                  Update available:{' '}
                  <strong style={{ color: updateCheck.update_available ? 'var(--accent, #b45309)' : undefined }}>
                    {updateCheck.update_available ? 'yes' : 'no'}
                  </strong>
                </li>
                <li>
                  Login prompt: <strong>{updateCheck.prompt_enabled ? 'enabled' : 'disabled'}</strong>
                </li>
                <li>
                  Deploy trigger configured:{' '}
                  <strong>{updateCheck.deploy_trigger_configured ? 'yes' : 'no'}</strong>
                  {' '}({updateCheck.compose_update_enabled ? 'Compose' : 'no Compose'},{' '}
                  {updateCheck.github_actions_configured ? 'GitHub Actions' : 'no GitHub Actions'})
                </li>
              </>
            ) : (
              <li>
                GitHub repo for update checks: <strong>not configured</strong>. Set{' '}
                <code>CANARY_GITHUB_DEPLOY_OWNER</code> and <code>CANARY_GITHUB_DEPLOY_REPO</code> (see{' '}
                <code>.env.example</code>).
              </li>
            )}
          </ul>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            {updateCheckBusy ? 'Checking…' : 'No data yet.'}
          </p>
        )}

        {updateCheck?.note ? (
          <p className="muted" style={{ marginTop: 8, fontSize: 13, lineHeight: 1.55 }}>{updateCheck.note}</p>
        ) : null}

        {updateCheck && updateCheck.update_available && updateCheck.commit_messages.length > 0 ? (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Commits on GitHub since this build</div>
            <ul style={{ margin: 0, paddingLeft: 18, maxHeight: 200, overflow: 'auto', fontSize: 13 }}>
              {updateCheck.commit_messages.map((m, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  {m}
                </li>
              ))}
            </ul>
            {updateCheck.compare_html_url ? (
              <a href={updateCheck.compare_html_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                View full compare on GitHub
              </a>
            ) : null}
          </div>
        ) : null}

        <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            type="button"
            className="btn primary"
            style={updateCheckBusy ? { cursor: 'wait' } : undefined}
            disabled={updateCheckBusy}
            onClick={() => void checkForUpdates()}
          >
            {updateCheckBusy ? 'Checking…' : 'Check now'}
          </button>
          {updateCheckAt ? (
            <span className="muted" style={{ fontSize: 13 }}>
              Last checked {updateCheckAt.toLocaleTimeString()}
            </span>
          ) : null}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Update this server (Docker Compose)</h3>
        <p className="muted" style={{ lineHeight: 1.55 }}>
          Recommended for self-hosting: administrators run Compose on the host without any GitHub token. Requires{' '}
          <code>CANARY_COMPOSE_UPDATE_ENABLED</code>, a mounted Docker socket, and the compose project directory (see{' '}
          <code>.env.example</code>). The initial request returns immediately; the page polls until{' '}
          <code>docker compose build</code>/<code>up</code> finish (works behind short proxy timeouts). Granting Docker
          socket access is powerful — restrict who has Admin.
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
          Optional: request <code>deploy-canary.yml</code> from here when the server has a PAT and self-hosted runner wired
          (see <code>.github/workflows/deploy-canary.yml</code>). If both Compose and GitHub are configured, the post-login
          “Update now” button uses Compose first.
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
          Neither apply-update path is configured — set Compose env vars and mounts (see <code>.env.example</code>), or
          configure GitHub Actions dispatch on the server (PAT + runner — see workflow file).
        </p>
      ) : null}
    </div>
  )
}
