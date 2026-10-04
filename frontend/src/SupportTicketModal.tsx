import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch } from './api'
import type { ApiError } from './api'

export type SupportTicketKind = 'support' | 'bug'

type Props = {
  open: boolean
  kind: SupportTicketKind
  onClose: () => void
  onSubmitted?: () => void
}

const URGENCY_OPTIONS: { value: number; hint: string }[] = [
  { value: 1, hint: 'Slight problem' },
  { value: 2, hint: 'Low' },
  { value: 3, hint: 'Normal' },
  { value: 4, hint: 'High' },
  { value: 5, hint: 'Urgent' },
]

export function SupportTicketModal({ open, kind, onClose, onSubmitted }: Props) {
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [urgency, setUrgency] = useState(3)
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const titleId = useId()
  const urgencyName = useId()

  const title = kind === 'bug' ? 'Report a bug' : 'Submit a support ticket'
  const confirmLabel = kind === 'bug' ? 'Send bug report' : 'Send support ticket'
  const urgencyHint = URGENCY_OPTIONS.find((o) => o.value === urgency)?.hint ?? ''

  // Reset only when the dialog opens or the ticket kind changes — not on parent re-renders.
  useEffect(() => {
    if (!open) return
    setSubject('')
    setMessage('')
    setUrgency(3)
    setPhone('')
    setErr(null)
    setBusy(false)
  }, [open, kind])

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, busy])

  if (!open) return null

  async function submit() {
    const sub = subject.trim()
    const msg = message.trim()
    if (!sub || !msg) {
      setErr('Please enter a subject and message.')
      return
    }
    if (urgency < 1 || urgency > 5) {
      setErr('Please choose an urgency from 1 to 5.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/support/ticket', {
        method: 'POST',
        json: {
          kind,
          subject: sub,
          message: msg,
          urgency,
          phone: phone.trim() || null,
        },
      })
      onSubmitted?.()
      onClose()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not send your message.')
    } finally {
      setBusy(false)
    }
  }

  return createPortal(
    <div className="modalOverlay" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="modal card" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
        <div className="paneHead">
          <div>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>
        <div className="stack" style={{ padding: '16px 22px 18px' }}>
          <p style={{ margin: 0, lineHeight: 1.45, color: 'var(--muted)' }}>
            Your message is e-mailed to Canary support. Include enough detail for us to reproduce the issue or
            answer your question.
          </p>
          <label className="field">
            <span>Subject</span>
            <input
              value={subject}
              disabled={busy}
              maxLength={200}
              autoFocus
              placeholder={kind === 'bug' ? 'Short summary of the bug' : 'What do you need help with?'}
              onChange={(e) => setSubject(e.target.value)}
            />
          </label>
          <fieldset className="field" style={{ border: 'none', margin: 0, padding: 0, minWidth: 0 }}>
            <legend style={{ padding: 0, marginBottom: 6, font: 'inherit' }}>
              Urgency <span style={{ color: 'var(--muted)', fontWeight: 400 }}>(1 = slight problem, 5 = urgent)</span>
            </legend>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }} role="radiogroup" aria-label="Urgency">
              {URGENCY_OPTIONS.map((opt) => {
                const selected = urgency === opt.value
                return (
                  <label
                    key={opt.value}
                    className={`btn${selected ? ' primary' : ''}`}
                    style={{
                      minWidth: 40,
                      justifyContent: 'center',
                      cursor: busy ? 'not-allowed' : 'pointer',
                      margin: 0,
                    }}
                    title={opt.hint}
                  >
                    <input
                      type="radio"
                      name={urgencyName}
                      value={opt.value}
                      checked={selected}
                      disabled={busy}
                      onChange={() => setUrgency(opt.value)}
                      style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}
                    />
                    {opt.value}
                  </label>
                )
              })}
            </div>
            <div style={{ marginTop: 6, fontSize: '0.875rem', color: 'var(--muted)' }}>{urgencyHint}</div>
          </fieldset>
          <label className="field">
            <span>
              Phone number <span style={{ color: 'var(--muted)', fontWeight: 400 }}>(optional)</span>
            </span>
            <input
              type="tel"
              value={phone}
              disabled={busy}
              maxLength={40}
              autoComplete="tel"
              placeholder="If we may call you about this"
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Details</span>
            <textarea
              rows={6}
              value={message}
              disabled={busy}
              maxLength={8000}
              placeholder={
                kind === 'bug'
                  ? 'What happened, what you expected, and steps to reproduce…'
                  : 'Describe your question or request…'
              }
              onChange={(e) => setMessage(e.target.value)}
              style={{ width: '100%', resize: 'vertical' }}
            />
          </label>
          {err ? <div className="error">{err}</div> : null}
          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => void submit()}
              disabled={busy || !subject.trim() || !message.trim()}
            >
              {busy ? 'Sending…' : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
