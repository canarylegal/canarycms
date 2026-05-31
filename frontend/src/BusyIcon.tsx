type Props = {
  /** Accessible label for screen readers. */
  label?: string
}

/** Compact loading spinner for short waits (e.g. opening a matter). */
export function BusyIcon({ label = 'Loading' }: Props) {
  return (
    <div className="busyIcon" role="status" aria-live="polite" aria-label={label}>
      <span className="busyIconSpinner" aria-hidden />
    </div>
  )
}
