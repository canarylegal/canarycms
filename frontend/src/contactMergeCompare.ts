import type { ContactMergePreviewOut, ContactOut } from './types'

export type ContactCompareField = {
  key: string
  label: string
  keep: string
  absorb: string
  mismatch: boolean
}

function display(value: string | null | undefined): string {
  const t = (value ?? '').trim()
  return t || '—'
}

function norm(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase()
}

function addressLines(c: ContactOut): string {
  const parts = [c.address_line1, c.address_line2, c.city, c.county, c.postcode, c.country]
    .map((p) => (p ?? '').trim())
    .filter(Boolean)
  return parts.length ? parts.join(', ') : '—'
}

function personNameParts(c: ContactOut): string {
  const parts = [c.title, c.first_name, c.middle_name, c.last_name]
    .map((p) => (p ?? '').trim())
    .filter(Boolean)
  return parts.length ? parts.join(' ') : display(c.name)
}

function orgNameParts(c: ContactOut): string {
  const trading = (c.trading_name ?? '').trim()
  const company = (c.company_name ?? '').trim()
  if (trading && company && trading.toLowerCase() !== company.toLowerCase()) {
    return `${trading} (${company})`
  }
  return trading || company || display(c.name)
}

function field(
  key: string,
  label: string,
  keepRaw: string | null | undefined,
  absorbRaw: string | null | undefined,
  opts?: { displayKeep?: string; displayAbsorb?: string },
): ContactCompareField {
  const keep = opts?.displayKeep ?? display(keepRaw)
  const absorb = opts?.displayAbsorb ?? display(absorbRaw)
  return {
    key,
    label,
    keep,
    absorb,
    mismatch: norm(keepRaw) !== norm(absorbRaw) && !(keep === '—' && absorb === '—'),
  }
}

/** Side-by-side rows for the merge review dialog. */
export function buildContactCompareFields(keep: ContactOut, absorb: ContactOut): ContactCompareField[] {
  const rows: ContactCompareField[] = [
    field('type', 'Type', keep.type, absorb.type, {
      displayKeep: keep.type === 'organisation' ? 'Organisation' : 'Person',
      displayAbsorb: absorb.type === 'organisation' ? 'Organisation' : 'Person',
    }),
  ]

  const keepIsOrg = keep.type === 'organisation'
  const absorbIsOrg = absorb.type === 'organisation'
  if (keepIsOrg || absorbIsOrg) {
    rows.push(
      field('display_name', 'Name', keepIsOrg ? orgNameParts(keep) : personNameParts(keep), absorbIsOrg ? orgNameParts(absorb) : personNameParts(absorb)),
      field('trading_name', 'Trading name', keep.trading_name, absorb.trading_name),
      field('company_name', 'Company name', keep.company_name, absorb.company_name),
    )
  } else {
    rows.push(
      field('display_name', 'Name', personNameParts(keep), personNameParts(absorb)),
      field('title', 'Title', keep.title, absorb.title),
      field('first_name', 'First name', keep.first_name, absorb.first_name),
      field('middle_name', 'Middle name', keep.middle_name, absorb.middle_name),
      field('last_name', 'Last name', keep.last_name, absorb.last_name),
    )
  }

  rows.push(
    field('email', 'E-mail', keep.email, absorb.email),
    field('phone', 'Phone', keep.phone, absorb.phone),
    field('address', 'Address', addressLines(keep), addressLines(absorb), {
      displayKeep: addressLines(keep),
      displayAbsorb: addressLines(absorb),
    }),
  )

  return rows
}

export function contactMergeImpactLines(
  preview: ContactMergePreviewOut,
  opts: { willEmail: boolean },
): string[] {
  const lines = [
    `Matter links: ${preview.source_matter_links} move onto the surviving contact (${preview.survivor_matter_links} already linked).`,
    `Portal folder shares: ${preview.source_grants} move` +
      (preview.survivor_grants ? ` (${preview.survivor_grants} already present).` : '.'),
    preview.will_reset_client_portal
      ? 'Client portal: both access codes revoked → a new code is issued for the surviving contact.'
      : 'Client portal: neither contact has active portal access.',
  ]
  if (preview.will_reset_matter_portal_cases > 0) {
    lines.push(
      `Matter exchange portal: ${preview.will_reset_matter_portal_cases} case code(s) will be reset.`,
    )
  }
  if (opts.willEmail && preview.survivor.email) {
    lines.push(`The new portal access code will be e-mailed to ${preview.survivor.email}.`)
  }
  return lines
}
