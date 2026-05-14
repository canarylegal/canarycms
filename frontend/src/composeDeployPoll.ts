import { apiFetch } from './api'
import type { AdminDeployComposeJobOut, AdminDeployTriggerOut } from './types'

const POLL_MS = 2500
/** Slightly longer than backend compose build timeout (3600s). */
const MAX_WAIT_MS = 2 * 3600 * 1000 + 120_000

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
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
    const st = await apiFetch<AdminDeployComposeJobOut>('/admin/deploy/compose-job', { token })

    if (st.status === 'running' && st.job_id && st.job_id !== expectId) {
      throw new Error('Another compose update started; stopping this wait.')
    }

    if (st.job_id === expectId) {
      if (st.status === 'succeeded') {
        return { message: st.message ?? out.message, usedComposeAsync: true }
      }
      if (st.status === 'failed') {
        const tail = st.log_excerpt ? `\n\n${st.log_excerpt}` : ''
        throw new Error(`${st.error_detail || 'Compose update failed.'}${tail}`)
      }
    }

    await sleep(POLL_MS)
  }

  throw new Error('Timed out waiting for compose update. Check Admin → Deploy or server logs.')
}
