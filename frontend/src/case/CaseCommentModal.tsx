import { useState } from 'react'
import { apiFetch, apiUrl } from '../api'
import { caseAuthHeaders } from './caseDetailHelpers'

export type CaseCommentModalProps = {
  caseId: string
  token: string
  docFolder: string
  commentEditFileId: string | null
  commentVersion: number | null
  setCommentVersion: (v: number | null) => void
  commentBusy: boolean
  setCommentBusy: (v: boolean) => void
  commentErr: string | null
  setCommentErr: (v: string | null) => void
  commentText: string
  setCommentText: (v: string) => void
  onClose: () => void
  onSaved: () => void
}

export function CaseCommentModal({
  caseId,
  token,
  docFolder,
  commentEditFileId,
  commentVersion,
  setCommentVersion,
  commentBusy,
  setCommentBusy,
  commentErr,
  setCommentErr,
  commentText,
  setCommentText,
  onClose,
  onSaved,
}: CaseCommentModalProps) {
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<{ text: string; version: number } | null>(null)

  return (
      <div
        className="modalOverlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="comment-modal-title"
        onClick={(e) => e.target === e.currentTarget && !commentBusy && onClose()}
      >
        <div className="modal card" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
          <div className="paneHead">
            <h2 id="comment-modal-title" style={{ margin: 0, fontSize: 18 }}>
              {commentEditFileId ? 'Edit comment' : 'New comment'}
            </h2>
            <button
              type="button"
              className="btn"
              disabled={commentBusy}
              onClick={onClose}
            >
              Cancel
            </button>
          </div>
          <div className="stack" style={{ marginTop: 12 }}>
            {commentErr ? <div className="error" role="alert">{commentErr}</div> : null}
            <textarea
              aria-label="Your comment draft"
              autoFocus
              rows={8}
              style={{ resize: 'vertical', width: '100%', boxSizing: 'border-box', fontFamily: 'inherit', fontSize: 14, padding: 8, borderRadius: 6, border: '1px solid #cbd5e1' }}
              placeholder="Type your comment here…"
              value={commentText}
              disabled={commentBusy}
              onChange={(e) => setCommentText(e.target.value)}
            />
            {conflict && commentEditFileId ? (
              <div className="stack">
                <p>Your draft is kept above. Load the latest comment, then combine both versions in your draft before saving.</p>
                <button type="button" className="btn" disabled={commentBusy} onClick={async () => {
                  setCommentBusy(true)
                  try {
                    const value = await apiFetch<{ text: string; version: number }>(`/cases/${caseId}/files/${commentEditFileId}/comment`, { token })
                    setLatest(value)
                    setCommentVersion(value.version)
                    setCommentErr(null)
                  } catch (e: unknown) {
                    setCommentErr((e as { message?: string })?.message ?? 'Could not load the latest comment')
                  } finally { setCommentBusy(false) }
                }}>Load latest comment</button>
                {latest ? <label>Latest saved comment<textarea readOnly rows={5} value={latest.text} /></label> : null}
              </div>
            ) : null}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn primary"
                disabled={commentBusy || !commentText.trim() || (!!commentEditFileId && (commentVersion === null || (conflict && !latest)))}
                onClick={async () => {
                  if (!caseId) return
                  setCommentBusy(true)
                  setCommentErr(null)
                  try {
                    if (commentEditFileId) {
                      // Edit mode: PATCH existing comment file
                      await apiFetch(`/cases/${caseId}/files/${commentEditFileId}/comment`, {
                        token,
                        method: 'PATCH',
                        json: { text: commentText, expected_version: commentVersion },
                      })
                    } else {
                      // Create mode: upload as new .txt file
                      const firstLine = commentText.trim().split('\n')[0].trim()
                      const label = firstLine.length > 80 ? firstLine.slice(0, 77) + '…' : firstLine
                      const filename = `${label || 'Comment'}.txt`
                      const blob = new Blob([commentText], { type: 'text/plain' })
                      const fd = new FormData()
                      fd.set('upload', blob, filename)
                      fd.set('folder', docFolder)
                      const res = await fetch(apiUrl(`/cases/${caseId}/files`), {
                        method: 'POST',
                        headers: caseAuthHeaders(token),
                        body: fd,
                      })
                      if (!res.ok) {
                        const body = await res.json().catch(() => ({}))
                        throw new Error((body as { detail?: string }).detail ?? res.statusText)
                      }
                    }
                    setCommentText('')
                    onClose()
                    onSaved()
                  } catch (e: any) {
                    if (e?.status === 409 && commentEditFileId) {
                      setConflict(true)
                      setLatest(null)
                      setCommentErr('The comment changed or is being edited. Your draft has not been saved. Review the latest comment before retrying.')
                    } else setCommentErr(e?.message ?? 'Failed to save comment')
                  } finally {
                    setCommentBusy(false)
                  }
                }}
              >
                {commentBusy ? 'Saving…' : 'Save comment'}
              </button>
            </div>
          </div>
        </div>
      </div>
  )
}
