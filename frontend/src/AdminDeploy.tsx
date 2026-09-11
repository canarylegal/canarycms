import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from './api'
import { AdminStorage } from './AdminStorage'
import type { ApiError } from './api'
import type { AdminDeployUpdateCheckOut } from './types'

export type AdminDeployStatusOut = {
  configured: boolean
  compose_update_enabled?: boolean
  compose_git_reset_enabled?: boolean
  compose_git_ref?: string
}

export function AdminDeploy({ token }: { token: string }) {
  const [status, setStatus] = useState<AdminDeployStatusOut | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [updateCheck, setUpdateCheck] = useState<AdminDeployUpdateCheckOut | null>(null)
  const [updateCheckBusy, setUpdateCheckBusy] = useState(false)
  const [updateCheckErr, setUpdateCheckErr] = useState<string | null>(null)
  const [updateCheckAt, setUpdateCheckAt] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setErr(null)
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

  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      {err ? <div className="error">{err}</div> : null}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Check for updates</h3>
        <p className="muted" style={{ lineHeight: 1.55 }}>
          Compares the backend image build commit against the configured GitHub ref tip (default:{' '}
          <code>latest-release</code>, so tag-pinned installs track GitHub Releases rather than floating{' '}
          <code>main</code>). The post-login
          prompt only runs once per session (and is silenced for any version dismissed with “Skip this version”); use
          this button to re-check at any time without logging out.
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
                <span>
                  {' '}
                  — image was built without the <code>GIT_COMMIT</code> build-arg, so updates cannot be detected.
                </span>
              ) : null}
            </li>
            {updateCheck.github_repo_configured ? (
              <>
                <li>
                  Remote ref: <strong>{updateCheck.remote_ref || '(default)'}</strong>
                </li>
                <li>
                  Remote tip: <strong>{updateCheck.remote_commit_short || '—'}</strong>
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
          <p className="muted" style={{ marginTop: 8, fontSize: 13, lineHeight: 1.55 }}>
            {updateCheck.note}
          </p>
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
        <h3 style={{ marginTop: 0 }}>How to update this server</h3>
        <p className="muted" style={{ lineHeight: 1.55 }}>
          Canary does not run Compose from the browser. Apply updates on the host over SSH (or your usual CI), then
          rebuild and restart. See <code>docs/DEPLOYMENT.md</code>.
        </p>
        <pre
          style={{
            marginTop: 12,
            padding: 12,
            overflow: 'auto',
            fontSize: 13,
            lineHeight: 1.45,
            background: 'var(--surface-2, #f4f4f5)',
            borderRadius: 6,
          }}
        >{`cd /path/to/canarycms
git pull --ff-only
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build
docker compose --profile prod up -d`}</pre>
        <p className="muted" style={{ marginTop: 12, fontSize: 13, lineHeight: 1.45 }}>
          In-app “Update now” was removed so the backend never needs the Docker socket. Status above stays notify-only
          {status?.compose_git_ref ? (
            <>
              {' '}
              (tracking <code>{status.compose_git_ref}</code>)
            </>
          ) : null}
          .
        </p>
      </div>

      <AdminStorage token={token} />
    </div>
  )
}
