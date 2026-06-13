import { useMemo, useState } from 'react'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import type { CasePropertyPayload, CasePropertyTenure } from '../types'

const TENURE_OPTIONS: { value: CasePropertyTenure; label: string }[] = [
  { value: 'freehold', label: 'Freehold' },
  { value: 'leasehold', label: 'Leasehold' },
  { value: 'commonhold', label: 'Commonhold' },
]

type Props = {
  draft: CasePropertyPayload
  onChange: (next: CasePropertyPayload) => void
  disabled?: boolean
}

/** Same field layout as the Property sub-menu editor in CaseDetail. */
export function PropertyDetailsForm({ draft, onChange, disabled }: Props) {
  const [tenureOpen, setTenureOpen] = useState(false)
  const tenureOptions = useMemo(
    () => TENURE_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
    [],
  )

  return (
    <div className="stack" style={{ marginTop: 12 }}>
      <div className="muted" style={{ fontWeight: 600 }}>
        Title number(s)
      </div>
      {draft.title_numbers.map((t, i) => (
        <div key={i} className="row" style={{ gap: 8 }}>
          <input
            style={{ flex: 1 }}
            value={t}
            disabled={disabled}
            onChange={(e) => {
              const next = [...draft.title_numbers]
              next[i] = e.target.value
              onChange({ ...draft, title_numbers: next })
            }}
          />
          <button
            type="button"
            className="btn"
            disabled={disabled}
            onClick={() => {
              const next = draft.title_numbers.filter((_, j) => j !== i)
              onChange({ ...draft, title_numbers: next })
            }}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn"
        disabled={disabled}
        onClick={() =>
          onChange({
            ...draft,
            title_numbers: [...draft.title_numbers, ''],
          })
        }
      >
        Add title number
      </button>
      <SingleSelectDropdown
        label="Tenure"
        options={tenureOptions}
        value={draft.tenure ?? ''}
        onChange={(v) =>
          onChange({
            ...draft,
            tenure: v === '' ? null : (v as CasePropertyTenure),
          })
        }
        open={tenureOpen}
        onOpenChange={setTenureOpen}
        disabled={disabled}
        placeholder="—"
      />
      <label className="row" style={{ alignItems: 'center', gap: 8 }}>
        <input
          type="checkbox"
          checked={draft.is_non_postal}
          disabled={disabled}
          onChange={(e) => onChange({ ...draft, is_non_postal: e.target.checked })}
        />
        <span>Non-postal address (free lines)</span>
      </label>
      {!draft.is_non_postal ? (
        <>
          <label className="field">
            <span>Address line 1</span>
            <input
              value={draft.uk.line1 ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, line1: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Address line 2</span>
            <input
              value={draft.uk.line2 ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, line2: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Town / city</span>
            <input
              value={draft.uk.town ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, town: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>County</span>
            <input
              value={draft.uk.county ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, county: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Postcode</span>
            <input
              value={draft.uk.postcode ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, postcode: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Country</span>
            <input
              value={draft.uk.country ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, country: e.target.value },
                })
              }
            />
          </label>
        </>
      ) : (
        [0, 1, 2, 3, 4, 5].map((i) => (
          <label key={i} className="field">
            <span>Address line {i + 1}</span>
            <input
              value={draft.free_lines[i] ?? ''}
              disabled={disabled}
              onChange={(e) => {
                const next = [...draft.free_lines]
                next[i] = e.target.value
                onChange({ ...draft, free_lines: next })
              }}
            />
          </label>
        ))
      )}
    </div>
  )
}
