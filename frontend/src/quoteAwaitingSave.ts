import { useEffect } from 'react'
import {
  isCanaryComposeDiscardedMessage,
  isCanaryComposePublishedMessage,
} from './caseFilesCrossTab'

export type QuoteAwaitingSaveContext = {
  caseId: string
  fileId: string
  preferredContactId: string | null
  portalEnabled: boolean
}

function idsMatch(a: string, b: string): boolean {
  return String(a) === String(b)
}

export function useQuoteAwaitingSave(
  context: QuoteAwaitingSaveContext | null,
  handlers: {
    onPublished: (ctx: QuoteAwaitingSaveContext) => void
    onDiscarded?: (ctx: QuoteAwaitingSaveContext) => void
  },
): void {
  const { onPublished, onDiscarded } = handlers

  useEffect(() => {
    if (!context) return
    const active = context

    function onMessage(e: MessageEvent) {
      if (e.origin !== window.location.origin) return
      const data = e.data
      if (isCanaryComposePublishedMessage(data)) {
        if (!idsMatch(data.caseId, active.caseId) || !idsMatch(data.fileId, active.fileId)) return
        onPublished(active)
        return
      }
      if (isCanaryComposeDiscardedMessage(data)) {
        if (!idsMatch(data.caseId, active.caseId) || !idsMatch(data.fileId, active.fileId)) return
        onDiscarded?.(active)
      }
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [context, onDiscarded, onPublished])
}
