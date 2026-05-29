import { useEffect, useRef, useState } from 'react'
import { apiFetch } from './api'
import { apiFetchWithRetry, postDeployTriggerAndWaitForCompose } from './composeDeployPoll'
import { ComposeUpdateProgress } from './ComposeUpdateProgress'
import { useDialogs } from './DialogProvider'
import type { ApiError } from './api'
import type { AdminDeployComposeJobOut, AdminDeployUpdateCheckOut, UserPublic } from './types'

const DISMISS_KEY = 'canary_update_prompt_dismissed_remote_sha'
const LATER_SESSION_KEY = 'canary_update_prompt_later_remote_sha'

export function AdminLoginUpdatePrompt({
  token,
  me,
  canAdmin,
}: {
  token: string
  me: UserPublic | null
  canAdmin: boolean
}) {
  const { alert } = useDialogs()
  const [data, setData] = useState<AdminDeployUpdateCheckOut | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [composeProgress, setComposeProgress] = useState<AdminDeployComposeJobOut | null>(null)
  const fetchedRef = useRef<string | null>(null)

  useEffect(() => {
    if (!canAdmin || !me) {
      setOpen(false)
      setData(null)
      return
    }
    const sessionKey = `${me.id}:${token.slice(0, 12)}`
    if (fetchedRef.current === sessionKey) return
    let cancelled = false
    void (async () => {
      try {
        const d = await apiFetch<AdminDeployUpdateCheckOut>('/admin/deploy/update-check', { token })
        if (cancelled) return
        fetchedRef.current = sessionKey
        if (!d.prompt_enabled || !d.update_available) {
          setOpen(false)
          setData(null)
          return
        }
        try {
          if (localStorage.getItem(DISMISS_KEY) === d.remote_commit) {
            setOpen(false)
            setData(null)
            return
          }
        } catch {
          /* private mode */
        }
        try {
          if (sessionStorage.getItem(LATER_SESSION_KEY) === d.remote_commit) {
            setOpen(false)
            setData(null)
            return
          }
        } catch {
          /* */
        }
        setData(d)
        setOpen(true)
      } catch {
        if (!cancelled) {
          fetchedRef.current = sessionKey
          setOpen(false)
          setData(null)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, me, canAdmin])

  function dismissForVersion() {
    if (!data) return
    try {
      localStorage.setItem(DISMISS_KEY, data.remote_commit)
    } catch {
      /* */
    }
    setOpen(false)
  }

  function remindLater() {
    if (!data) return
    try {
      sessionStorage.setItem(LATER_SESSION_KEY, data.remote_commit)
    } catch {
      /* */
    }
    setOpen(false)
  }

  async function executeDeploy() {
    if (!data || !me) return
    if (!data.deploy_trigger_configured) {
      setErr('Updates from the UI are not configured on this server.')
      return
    }
    setBusy(true)
    setErr(null)
    setComposeProgress(null)
    try {
      const { message, usedComposeAsync } = await postDeployTriggerAndWaitForCompose(
        token,
        { method: 'auto' },
        { onProgress: setComposeProgress },
      )
      setOpen(false)
      await alert(message, usedComposeAsync ? 'Update applied' : 'Update')
      const sessionKey = `${me.id}:${token.slice(0, 12)}`
      try {
        const d = await apiFetchWithRetry<AdminDeployUpdateCheckOut>('/admin/deploy/update-check', token)
        fetchedRef.current = sessionKey
        if (!d.prompt_enabled || !d.update_available) {
          setData(null)
        }
      } catch {
        fetchedRef.current = sessionKey
        setData(null)
      }
    } catch (e) {
      setErr((e as ApiError).message ?? 'Deploy request failed')
    } finally {
      setBusy(false)
      setComposeProgress(null)
    }
  }

  if (!open || !data) return null

  return (
    <div
      className="modalOverlay"
      style={{ zIndex: 10050 }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="canary-update-prompt-title"
    >
      <div className="modal card" style={{ maxWidth: 560, padding: 20 }} onClick={(e) => e.stopPropagation()}>
        <h2 id="canary-update-prompt-title" style={{ margin: '0 0 8px', fontSize: 18 }}>
          {busy ? 'Updating…' : 'Update available'}
        </h2>
        {!busy ? (
          <p className="muted" style={{ margin: '0 0 12px', lineHeight: 1.45 }}>
            A newer version is available on GitHub ({data.remote_ref}, tip{' '}
            <code>{data.remote_commit_short}</code>).
          </p>
        ) : (
          <p className="muted" style={{ margin: '0 0 12px', lineHeight: 1.45, fontSize: 13 }}>
            This may take several minutes. The page will finish when the update completes.
          </p>
        )}
        {data.note && !busy ? (
          <p className="muted" style={{ margin: '0 0 12px', fontSize: 13 }}>
            {data.note}
          </p>
        ) : null}
        {err ? <div className="error" style={{ marginBottom: 10 }}>{err}</div> : null}

        {busy ? <ComposeUpdateProgress progress={composeProgress} /> : null}

        {!busy && (data.latest_release_name || data.latest_release_tag) ? (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Latest GitHub release</div>
            <div className="muted" style={{ fontSize: 14 }}>
              {data.latest_release_name ?? data.latest_release_tag}
              {data.latest_release_tag && data.latest_release_name ? ` (${data.latest_release_tag})` : null}
            </div>
            {data.latest_release_body ? (
              <pre
                style={{
                  marginTop: 8,
                  maxHeight: 220,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  fontSize: 13,
                  lineHeight: 1.45,
                  padding: 10,
                  background: 'var(--surface-2, #f4f4f5)',
                  borderRadius: 6,
                }}
              >
                {data.latest_release_body}
              </pre>
            ) : null}
          </div>
        ) : null}

        {!busy && data.commit_messages.length > 0 ? (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Recent changes</div>
            <ul style={{ margin: 0, paddingLeft: 18, maxHeight: 200, overflow: 'auto', fontSize: 13 }}>
              {data.commit_messages.map((m, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  {m}
                </li>
              ))}
            </ul>
            {data.compare_html_url ? (
              <a href={data.compare_html_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                View full compare on GitHub
              </a>
            ) : null}
          </div>
        ) : null}

        <div className="row" style={{ gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end', marginTop: 16 }}>
          {!busy ? (
            <>
              <button type="button" className="btn" onClick={remindLater}>
                Later
              </button>
              <button type="button" className="btn" onClick={dismissForVersion}>
                Skip this version
              </button>
              <button
                type="button"
                className="btn primary"
                style={!data.deploy_trigger_configured ? { opacity: 0.55, cursor: 'not-allowed' } : undefined}
                title={data.deploy_trigger_configured ? undefined : 'Compose updates are not configured on this server.'}
                onClick={() => void executeDeploy()}
              >
                Update now
              </button>
            </>
          ) : (
            <button type="button" className="btn" disabled>
              Updating…
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
