import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { AlertModal } from './AlertModal'
import { ConfirmModal } from './ConfirmModal'

export type ConfirmOptions = {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  /** When set, shows a third button; use askConfirmChoice to read the result. */
  secondaryLabel?: string
  danger?: boolean
}

export type ConfirmChoice = 'confirm' | 'secondary' | 'cancel'

type DialogContextValue = {
  askConfirm: (opts: ConfirmOptions) => Promise<boolean>
  /** Three-way confirm when `secondaryLabel` is set. */
  askConfirmChoice: (opts: ConfirmOptions & { secondaryLabel: string }) => Promise<ConfirmChoice>
  alert: (message: string, title?: string) => Promise<void>
}

type ConfirmQueued = {
  kind: 'confirm'
  opts: ConfirmOptions
  resolve: (v: ConfirmChoice) => void
}

type AlertQueued = {
  kind: 'alert'
  title: string
  message: string
  resolve: () => void
}

type QueuedDialog = ConfirmQueued | AlertQueued

const DialogContext = createContext<DialogContextValue | null>(null)

export function useDialogs(): DialogContextValue {
  const v = useContext(DialogContext)
  if (!v) {
    throw new Error('useDialogs must be used within DialogProvider')
  }
  return v
}

/** Optional: no-op when provider missing (e.g. standalone pages). */
export function useDialogsOptional(): DialogContextValue | null {
  return useContext(DialogContext)
}

export function DialogProvider({ children }: { children: ReactNode }) {
  const queueRef = useRef<QueuedDialog[]>([])
  const [active, setActive] = useState<QueuedDialog | null>(null)

  const pump = useCallback(() => {
    setActive(queueRef.current[0] ?? null)
  }, [])

  const enqueueConfirm = useCallback(
    (opts: ConfirmOptions) => {
      return new Promise<ConfirmChoice>((resolve) => {
        queueRef.current.push({ kind: 'confirm', opts, resolve })
        pump()
      })
    },
    [pump],
  )

  const askConfirmChoice = useCallback(
    (opts: ConfirmOptions & { secondaryLabel: string }) => enqueueConfirm(opts),
    [enqueueConfirm],
  )

  const askConfirm = useCallback(
    (opts: ConfirmOptions) => {
      const { secondaryLabel: _ignored, ...rest } = opts
      return enqueueConfirm(rest).then((choice) => choice === 'confirm')
    },
    [enqueueConfirm],
  )

  const alertFn = useCallback(
    (message: string, title = 'Notice') => {
      return new Promise<void>((resolve) => {
        queueRef.current.push({ kind: 'alert', title, message, resolve })
        pump()
      })
    },
    [pump],
  )

  const finishActive = useCallback(() => {
    queueRef.current.shift()
    pump()
  }, [pump])

  const value = useMemo(
    () => ({ askConfirm, askConfirmChoice, alert: alertFn }),
    [askConfirm, askConfirmChoice, alertFn],
  )

  return (
    <DialogContext.Provider value={value}>
      {children}
      {active?.kind === 'confirm' ? (
        <ConfirmModal
          open
          title={active.opts.title}
          message={active.opts.message}
          confirmLabel={active.opts.confirmLabel ?? 'Confirm'}
          cancelLabel={active.opts.cancelLabel ?? 'Cancel'}
          secondaryLabel={active.opts.secondaryLabel}
          danger={active.opts.danger}
          onConfirm={() => {
            active.resolve('confirm')
            finishActive()
          }}
          onCancel={() => {
            active.resolve('cancel')
            finishActive()
          }}
          onSecondary={
            active.opts.secondaryLabel
              ? () => {
                  active.resolve('secondary')
                  finishActive()
                }
              : undefined
          }
        />
      ) : null}
      {active?.kind === 'alert' ? (
        <AlertModal
          open
          title={active.title}
          message={active.message}
          onClose={() => {
            active.resolve()
            finishActive()
          }}
        />
      ) : null}
    </DialogContext.Provider>
  )
}
