import { useEffect, useRef, useState } from 'react'
import { apiFetch, COOKIE_SESSION_TOKEN } from '../api'
import { SESSION_EXPIRED, sessionUserId } from './sessionRecovery'

/** Leave the application/editor mounted: no navigation, discarded drafts or automatic writes. */
export function SessionRecovery() {
  const [expired, setExpired] = useState(false)
  const [message, setMessage] = useState('')
  const [checking, setChecking] = useState(false)
  const expectedUser = useRef<string | null>(null)
  useEffect(() => {
    let cancelled = false
    // Standalone editor tabs do not mount useAuth; capture their original account too.
    if (!sessionUserId()) {
      void apiFetch<{ id: string }>('/auth/me', { token: COOKIE_SESSION_TOKEN }).then(user => {
        if (!cancelled && !expectedUser.current) expectedUser.current = user.id
      }).catch(() => { /* A normal signed-out page does not need a recovery notice. */ })
    }
    const onExpired = () => {
      if (!expectedUser.current) expectedUser.current = sessionUserId()
      setExpired(true)
    }
    window.addEventListener(SESSION_EXPIRED, onExpired)
    return () => { cancelled = true; window.removeEventListener(SESSION_EXPIRED, onExpired) }
  }, [])
  if (!expired) return null
  return <div role="alert" style={{ position: 'fixed', bottom: 16, right: 16, zIndex: 20000, maxWidth: 440, padding: 16, background: 'white', color: '#172554', border: '1px solid #94a3b8', borderRadius: 8, boxShadow: '0 4px 16px #0003' }}>
    <strong>Your session has expired.</strong>
    <p>Keep this window open. Sign in with the same account in another tab, then return and retry your action. Your selected files and unsaved work remain here.</p>
    <a href="/" target="_blank" rel="noopener noreferrer">Sign in in another tab</a>{' '}
    <button type="button" disabled={checking} onClick={async () => {
      setChecking(true)
      try {
        const user = await apiFetch<{ id: string }>('/auth/me', { token: COOKIE_SESSION_TOKEN })
        if (expectedUser.current && user.id !== expectedUser.current) {
          setMessage('A different account is signed in. Sign in with the original account before retrying.')
          return
        }
        setExpired(false); setMessage(''); expectedUser.current = null
      } catch { setMessage('You are not signed in yet. Complete sign-in in the other tab, then try again.') }
      finally { setChecking(false) }
    }}>I’ve signed in</button>
    {message && <p>{message}</p>}
  </div>
}
