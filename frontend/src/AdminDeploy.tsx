import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from './api'
import { postDeployTriggerAndWaitForCompose } from './composeDeployPoll'
import { ComposeUpdateProgress } from './ComposeUpdateProgress'
import { useDialogs } from './DialogProvider'
import type { ApiError } from './api'
import type { AdminDeployComposeJobOut, AdminDeployUpdateCheckOut } from './types'

export type AdminDeployStatusOut = {
  configured: boolean
  compose_update_enabled?: boolean
  compose_git_reset_enabled?: boolean
  compose_git_ref?: string
}

export function AdminDeploy({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [status, setStatus] = useState<AdminDeployStatusOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)
  const [updateCheck, setUpdateCheck] = useState<AdminDeployUpdateCheckOut | null>(null)
  const [updateCheckBusy, setUpdateCheckBusy] = useState(false)
  const [updateCheckErr, setUpdateCheckErr] = useState<string | null>(null)
  const [updateCheckAt, setUpdateCheckAt] = useState<Date | null>(null)
  const [composeProgress, setComposeProgress] = useState<AdminDeployComposeJobOut | null>(null)
  const [finishing, setFinishing] = useState(false)

  const load = useCallback(async () => {
    setErr(null)
    setOk(null)
    try {
      const s = await apiFetch<AdminDeployStatusOut>('/admin/deploy/status', { token })
      setStatus(s)
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

  async function triggerCompose(gitStrategy: 'ff-only' | 'reset' = 'ff-only') {
    const isReset = gitStrategy === 'reset'
    if (isReset) {
      const gitRef = status?.compose_git_ref || updateCheck?.compose_git_ref || 'main'
      const confirmed = await askConfirm({
        title: 'Reset to GitHub and update',
        message: `This discards any local changes on the server and updates from GitHub (${gitRef}). Continue?`,
        danger: true,
        confirmLabel: 'Reset and update',
      })
      if (!confirmed) return
    }
    setBusy(true)
    setErr(null)
    setOk(null)
    setComposeProgress(null)
    setFinishing(false)
    try {
      const { reloadApp } = await postDeployTriggerAndWaitForCompose(
        token,
        {
          method: 'compose',
          git_strategy: gitStrategy,
        },
        { onProgress: setComposeProgress, onFinishing: () => setFinishing(true) },
      )
      if (reloadApp) {
        window.location.reload()
        return
      }
      setOk('Update complete.')
      await load()
      await checkForUpdates()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Compose update failed')
    } finally {
      setBusy(false)
      setComposeProgress(null)
      setFinishing(false)
    }
  }

  const composeOn = Boolean(status?.compose_update_enabled)
  const resetOn = Boolean(status?.compose_git_reset_enabled)

  return (
    <div className="stack" style={{ maxWidth: 560 }}>
      {err ? <div className="error">{err}</div> : null}
      {ok ? <div className="muted">{ok}</div> : null}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Check for updates</h3>
        <p className="muted" style={{ lineHeight: 1.55 }}>
          Compares the backend image build commit against the tip of the configured public GitHub branch. The post-login prompt
          only runs once per session (and is silenced for any version dismissed with “Skip this version”); use this
          button to re-check at any time without logging out.
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
                  Compose update from UI:{' '}
                  <strong>{updateCheck.compose_update_enabled ? 'enabled' : 'not configured'}</strong>
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
          Administrators run Compose on the host from here (no GitHub token). Requires{' '}
          <code>CANARY_COMPOSE_UPDATE_ENABLED</code>, a mounted Docker socket, and the compose project directory (see{' '}
          <code>.env.example</code>). The initial request returns immediately; the page polls until{' '}
          <code>docker compose build</code>/<code>up</code> finish (works behind short proxy timeouts). Granting Docker
          socket access is powerful — restrict who has Admin.
        </p>
        {composeOn ? (
          <p className="muted" style={{ marginTop: 12 }}>
            Compose-based updates are <strong>enabled</strong> on this server.
            {resetOn ? (
              <>
                {' '}
                <strong>Reset to GitHub</strong> is enabled (<code>CANARY_COMPOSE_GIT_RESET_ENABLED</code>) — use when{' '}
                <code>git pull --ff-only</code> fails because the checkout has local commits or diverged.
              </>
            ) : null}
          </p>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            Compose-based updates are <strong>not configured</strong>.
          </p>
        )}
        <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn primary"
            disabled={busy || !composeOn}
            onClick={() => void triggerCompose('ff-only')}
          >
            {busy ? 'Working…' : 'Run Compose update'}
          </button>
          {resetOn ? (
            <button
              type="button"
              className="btn"
              disabled={busy || !composeOn}
              title={`git fetch + reset --hard origin/${status?.compose_git_ref || 'main'}, then compose build/up`}
              style={{ borderColor: 'var(--danger, #dc2626)', color: 'var(--danger, #dc2626)' }}
              onClick={() => void triggerCompose('reset')}
            >
              {busy ? 'Working…' : 'Reset to GitHub & update'}
            </button>
          ) : null}
          <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
            Reload
          </button>
        </div>
        {busy ? (
          finishing ? (
            <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>
              Update complete — waiting for services to restart, then this page will reload…
            </p>
          ) : (
            <ComposeUpdateProgress progress={composeProgress} />
          )
        ) : null}
      </div>

      {!status?.configured ? (
        <p className="muted" style={{ marginTop: 12 }}>
          Compose updates are not configured — set <code>CANARY_COMPOSE_*</code> env vars and mounts (see{' '}
          <code>.env.example</code>).
        </p>
      ) : null}
    </div>
  )
}
