import { apiFetch } from './api'
import type { AdminDeployComposeJobOut, AdminDeployTriggerOut } from './types'

const POLL_MS = 2500
/** Slightly longer than backend compose build timeout (3600s). */
const MAX_WAIT_MS = 2 * 3600 * 1000 + 120_000

const POLL_FETCH_RETRIES = 6
const POLL_FETCH_RETRY_MS = 3000

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/** ``docker compose up`` may briefly recreate nginx/backend; tolerate 502/503 and network errors. */
async function apiFetchWithRetry<T>(path: string, token: string): Promise<T> {
  let last: unknown
  for (let attempt = 0; attempt < POLL_FETCH_RETRIES; attempt++) {
    try {
      return await apiFetch<T>(path, { token })
    } catch (e) {
      last = e
      const err = e as { status?: number; message?: string }
      const retry =
        err?.status === 502 ||
        err?.status === 503 ||
        err?.status === 504 ||
        (typeof err?.message === 'string' && /failed to fetch|networkerror|load failed/i.test(err.message))
      if (!retry || attempt === POLL_FETCH_RETRIES - 1) throw e
      await sleep(POLL_FETCH_RETRY_MS)
    }
  }
  throw last
}

/**
 * POST /admin/deploy/trigger then poll GET /admin/deploy/compose-job until the returned job finishes.
 * HTTP returns immediately so reverse proxies (e.g. Cloudflare) do not time out during docker build.
 */
export async function postDeployTriggerAndWaitForCompose(
  token: string,
  body: { method: 'auto' | 'compose' | 'github'; ref?: string | null; environment?: string | null },
): Promise<{ message: string; usedComposeAsync: boolean }> {
  const out = await apiFetch<AdminDeployTriggerOut>('/admin/deploy/trigger', {
    token,
    method: 'POST',
    json: body,
  })
  if (!out.async_mode || !out.job_id) {
    return { message: out.message, usedComposeAsync: false }
  }
  const expectId = out.job_id
  const deadline = Date.now() + MAX_WAIT_MS

  while (Date.now() < deadline) {
    const st = await apiFetchWithRetry<AdminDeployComposeJobOut>('/admin/deploy/compose-job', token)

    if (st.status === 'running' && st.job_id && st.job_id !== expectId) {
      throw new Error('Another compose update started; stopping this wait.')
    }

    if (st.job_id === expectId) {
      if (st.status === 'succeeded') {
        return { message: st.message ?? out.message, usedComposeAsync: true }
      }
      if (st.status === 'failed') {
        const detail = st.error_detail || ''
        if (detail.includes('restarted during the update')) {
          return {
            message:
              'The server restarted the API container during the update (normal for Docker Compose). ' +
              'Refresh this page. If the site loads, the update likely finished; otherwise check Admin → Deploy or host logs.',
            usedComposeAsync: true,
          }
        }
        const tail = st.log_excerpt ? `\n\n${st.log_excerpt}` : ''
        throw new Error(`${detail || 'Compose update failed.'}${tail}`)
      }
    }

    await sleep(POLL_MS)
  }

  throw new Error('Timed out waiting for compose update. Check Admin → Deploy or server logs.')
}
