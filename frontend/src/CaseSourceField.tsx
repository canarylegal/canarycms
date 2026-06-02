import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { CaseSourceOut } from './types'

export const CASE_SOURCE_CUSTOM = '__custom__'

export function useCaseSources(token: string) {
  const [sources, setSources] = useState<CaseSourceOut[]>([])

  useEffect(() => {
    let cancelled = false
    void apiFetch<CaseSourceOut[]>('/case-sources', { token })
      .then((data) => {
        if (!cancelled) setSources(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setSources([])
      })
    return () => {
      cancelled = true
    }
  }, [token])

  return sources
}

export function resolveCaseSourcePayload(
  sources: CaseSourceOut[],
  sourceId: string,
  customName: string,
): { source_id?: string; source_name?: string } {
  if (sourceId && sourceId !== CASE_SOURCE_CUSTOM) return { source_id: sourceId }
  const trimmed = customName.trim()
  if (!trimmed) return {}
  const match = sources.find((s) => s.name.toLowerCase() === trimmed.toLowerCase())
  if (match) return { source_id: match.id }
  return { source_name: trimmed }
}

type CaseSourceFieldProps = {
  sources: CaseSourceOut[]
  sourceId: string
  customName: string
  onSourceIdChange: (sourceId: string) => void
  onCustomNameChange: (name: string) => void
  disabled?: boolean
}

export function CaseSourceField({
  sources,
  sourceId,
  customName,
  onSourceIdChange,
  onCustomNameChange,
  disabled,
}: CaseSourceFieldProps) {
  return (
    <>
      <label className="field">
        <span>Source</span>
        <select value={sourceId} onChange={(e) => onSourceIdChange(e.target.value)} disabled={disabled}>
          <option value="">— select —</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
          <option value={CASE_SOURCE_CUSTOM}>Other (type below)…</option>
        </select>
      </label>
      {sourceId === CASE_SOURCE_CUSTOM ? (
        <label className="field">
          <span>Source name</span>
          <input
            type="text"
            value={customName}
            onChange={(e) => onCustomNameChange(e.target.value)}
            disabled={disabled}
            placeholder="Type a new source"
          />
        </label>
      ) : null}
    </>
  )
}
