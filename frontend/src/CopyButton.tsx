import { useEffect, useState } from 'react'
import { copyTextToClipboard } from './copyToClipboard'

type Props = {
  text: string
  label?: string
  copiedLabel?: string
  className?: string
  disabled?: boolean
  primary?: boolean
}

export function CopyButton({
  text,
  label = 'Copy',
  copiedLabel = 'Copied',
  className = 'btn',
  disabled = false,
  primary = false,
}: Props) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 2000)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function handleClick() {
    const ok = await copyTextToClipboard(text)
    if (ok) setCopied(true)
  }

  return (
    <button
      type="button"
      className={primary ? `btn primary${className !== 'btn' ? ` ${className}` : ''}` : className}
      disabled={disabled}
      onClick={() => void handleClick()}
    >
      {copied ? copiedLabel : label}
    </button>
  )
}
