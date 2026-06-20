import { useState } from 'react'
import { SendQuoteViaPortalModal } from './SendQuoteViaPortalModal'

type Props = {
  token: string
  caseId: string
  fileId: string
  preferredContactId?: string | null
  portalEnabled?: boolean
  open: boolean
  onClose: () => void
  onSendLetter: (caseId: string) => void
  onSendEmail: (caseId: string) => void
  onSent?: () => void
}

export function QuoteSendPrompt({
  token,
  caseId,
  fileId,
  preferredContactId = null,
  portalEnabled = false,
  open,
  onClose,
  onSendLetter,
  onSendEmail,
  onSent,
}: Props) {
  const [portalSendOpen, setPortalSendOpen] = useState(false)

  if (!open) return null

  return (
    <>
      <div className="modalOverlay" role="dialog" aria-modal="true">
        <div className="modal card modal--scrollBody modal--quoteWizard" onClick={(e) => e.stopPropagation()}>
          <div className="paneHead">
            <h2 style={{ margin: 0, fontSize: 18 }}>Send quote</h2>
            <button type="button" className="btn" onClick={onClose}>
              Close
            </button>
          </div>
          <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
            <p className="muted" style={{ marginTop: 0 }}>
              Your quote is saved. How would you like to send it?
            </p>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn primary"
                onClick={() => {
                  onSendEmail(caseId)
                  onClose()
                }}
              >
                Send by e-mail
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  onSendLetter(caseId)
                  onClose()
                }}
              >
                Send by letter
              </button>
              {portalEnabled ? (
                <button type="button" className="btn" onClick={() => setPortalSendOpen(true)}>
                  Send via portal
                </button>
              ) : null}
              <button type="button" className="btn" onClick={onClose}>
                Not now
              </button>
            </div>
          </div>
        </div>
      </div>
      <SendQuoteViaPortalModal
        token={token}
        caseId={caseId}
        fileId={fileId}
        preferredContactId={preferredContactId}
        open={portalSendOpen}
        onClose={() => setPortalSendOpen(false)}
        onSent={onSent}
      />
    </>
  )
}
