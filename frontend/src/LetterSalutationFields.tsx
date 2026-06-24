import { useMemo, useState } from 'react'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import {
  coerceLetterSalutation,
  defaultLetterSalutation,
  letterSalutationOptions,
  type LetterSalutation,
} from './letterSalutation'

export function LetterSalutationFields({
  matterContactType,
  contactType,
  value,
  customValue,
  onChange,
  busy,
}: {
  matterContactType: string
  contactType: 'person' | 'organisation'
  value: LetterSalutation | null | undefined
  customValue: string | null | undefined
  onChange: (patch: { letterSalutation: LetterSalutation; letterSalutationCustom: string | null }) => void
  busy?: boolean
}) {
  const [open, setOpen] = useState(false)
  const options = useMemo(
    () => letterSalutationOptions(matterContactType, contactType),
    [matterContactType, contactType],
  )
  const resolved = coerceLetterSalutation(value, matterContactType, contactType)

  return (
    <>
      <SingleSelectDropdown
        label="Letter salutation"
        options={options}
        value={resolved}
        onChange={(next) => {
          const salutation = coerceLetterSalutation(next, matterContactType, contactType)
          onChange({
            letterSalutation: salutation,
            letterSalutationCustom: salutation === 'custom' ? customValue ?? '' : null,
          })
        }}
        open={open}
        onOpenChange={setOpen}
        disabled={busy}
        placeholder="Select salutation"
      />
      {resolved === 'custom' ? (
        <label className="field">
          <span>Custom salutation</span>
          <input
            value={customValue ?? ''}
            onChange={(e) =>
              onChange({
                letterSalutation: 'custom',
                letterSalutationCustom: e.target.value,
              })
            }
            placeholder='e.g. Sir / Madam or full "Dear …" line'
            disabled={busy}
          />
        </label>
      ) : null}
    </>
  )
}

export function defaultLetterSalutationForContact(
  matterContactType: string,
  contactType: 'person' | 'organisation',
): { letterSalutation: LetterSalutation; letterSalutationCustom: null } {
  return {
    letterSalutation: defaultLetterSalutation(matterContactType, contactType),
    letterSalutationCustom: null,
  }
}
