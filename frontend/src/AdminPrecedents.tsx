import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import {
  suggestedPrecedentReferenceHex,
  precedentDisplayNameFromFile,
} from './admin/precedentAdminHelpers'
import { AdminLetterheadPanel } from './admin/AdminLetterheadPanel'
import { AdminSignaturePanel } from './admin/AdminSignaturePanel'
import { AdminMergeCodesPanel } from './admin/AdminMergeCodesPanel'
import { AdminPrecedentLibraryPanel } from './admin/AdminPrecedentLibraryPanel'
import type {
  FirmSettingsOut,
  MatterHeadTypeOut,
  PrecedentCategoryOut,
  PrecedentOut,
} from './types'
import { GLOBAL_PRECEDENT_SCOPE } from './types'

export {
  suggestedPrecedentReferenceHex,
  PrecedentNamePencilIcon,
  precedentDisplayNameFromFile,
} from './admin/precedentAdminHelpers'

export function AdminPrecedents({ token }: { token: string }) {
  const [items, setItems] = useState<PrecedentOut[]>([])
  const [matterHeads, setMatterHeads] = useState<MatterHeadTypeOut[]>([])
  const [uploadHeadTypeId, setUploadHeadTypeId] = useState('')
  const [uploadSubTypeId, setUploadSubTypeId] = useState('')
  const [uploadCats, setUploadCats] = useState<PrecedentCategoryOut[]>([])
  const [uploadCatsLoading, setUploadCatsLoading] = useState(false)
  const [uploadCatsFetchErr, setUploadCatsFetchErr] = useState<string | null>(null)
  /** Specific category id, or GLOBAL_PRECEDENT_SCOPE for “all categories under sub-type”. */
  const [uploadCategoryId, setUploadCategoryId] = useState(GLOBAL_PRECEDENT_SCOPE)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [reference, setReference] = useState(() => suggestedPrecedentReferenceHex())
  const [kind, setKind] = useState<'letter' | 'email' | 'document'>('letter')
  const [file, setFile] = useState<File | null>(null)
  const [firmSettings, setFirmSettings] = useState<FirmSettingsOut | null>(null)

  const matterTypeOptions = useMemo(
    () => matterHeads.map((h) => ({ id: h.id, label: h.name })),
    [matterHeads],
  )

  const uploadSubTypeOptions = useMemo(() => {
    if (!uploadHeadTypeId || uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE) return []
    const h = matterHeads.find((x) => x.id === uploadHeadTypeId)
    return (h?.sub_types ?? []).map((s) => ({ id: s.id, label: s.name }))
  }, [matterHeads, uploadHeadTypeId])

  const headIsGlobal = uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE

  const uploadHeadTypeDropdownOptions = useMemo(
    () => [
      { value: '', label: '— select —' },
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all cases)' },
      ...matterTypeOptions.map((o) => ({ value: o.id, label: o.label })),
    ],
    [matterTypeOptions],
  )

  const uploadSubTypeDropdownOptions = useMemo(() => {
    if (!uploadHeadTypeId) return [{ value: '', label: 'Select a matter type first' }]
    if (headIsGlobal) return [{ value: GLOBAL_PRECEDENT_SCOPE, label: 'Global' }]
    if (uploadSubTypeOptions.length === 0) return [{ value: '', label: 'No sub-types for this matter type' }]
    return [
      { value: '', label: '— select —' },
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all sub-types under this matter type)' },
      ...uploadSubTypeOptions.map((o) => ({ value: o.id, label: o.label })),
    ]
  }, [uploadHeadTypeId, headIsGlobal, uploadSubTypeOptions])

  const uploadCategoryDropdownOptions = useMemo(
    () => [
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all categories under this sub-type)' },
      ...uploadCats.map((c) => ({ value: c.id, label: c.name })),
    ],
    [uploadCats],
  )

  const uploadBlockers = useMemo(() => {
    const blockers: string[] = []
    if (uploadCatsLoading) blockers.push('Wait for precedent categories to finish loading')
    if (!name.trim()) blockers.push('Enter a precedent name')
    if (!reference.trim()) blockers.push('Enter a reference')
    if (!file) blockers.push('Choose a .docx file to upload')
    if (!uploadHeadTypeId) blockers.push('Select a matter type (or Global)')
    else if (!headIsGlobal && !uploadSubTypeId) blockers.push('Select a sub-type (or Global)')
    else if (
      !headIsGlobal &&
      uploadSubTypeId &&
      uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
      !uploadCategoryId
    ) {
      blockers.push('Select a precedent category (or Global)')
    }
    return blockers
  }, [
    uploadCatsLoading,
    name,
    reference,
    file,
    uploadHeadTypeId,
    headIsGlobal,
    uploadSubTypeId,
    uploadCategoryId,
  ])

  const uploadReady = uploadBlockers.length === 0

  useEffect(() => {
    if (
      !uploadSubTypeId ||
      uploadSubTypeId === GLOBAL_PRECEDENT_SCOPE ||
      uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE
    ) {
      setUploadCats([])
      setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
      setUploadCatsFetchErr(null)
      return
    }
    setUploadCatsLoading(true)
    setUploadCatsFetchErr(null)
    void apiFetch<PrecedentCategoryOut[]>(`/matter-types/sub-types/${uploadSubTypeId}/precedent-categories`, { token })
      .then((list) => {
        setUploadCats(list)
        setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
      })
      .catch((e: unknown) => {
        setUploadCats([])
        setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
        setUploadCatsFetchErr((e as ApiError)?.message ?? 'Could not load precedent categories for this sub-type')
      })
      .finally(() => setUploadCatsLoading(false))
  }, [uploadSubTypeId, uploadHeadTypeId, token])

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const [data, heads, firm] = await Promise.all([
        apiFetch<PrecedentOut[]>('/precedents', { token }),
        apiFetch<MatterHeadTypeOut[]>('/matter-types', { token }),
        apiFetch<FirmSettingsOut>('/admin/firm-settings', { token }),
      ])
      setItems(data)
      setMatterHeads(heads)
      setFirmSettings(firm)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load precedents')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  useEffect(() => {
    if (uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE) {
      setUploadSubTypeId(GLOBAL_PRECEDENT_SCOPE)
      setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
    }
  }, [uploadHeadTypeId])

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Precedents</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Refresh
        </button>
      </div>
      {err ? <div className="error">{err}</div> : null}

      <AdminLetterheadPanel
        token={token}
        firmSettings={firmSettings}
        onReload={load}
        onFirmSettings={setFirmSettings}
        onError={setErr}
      />
      <AdminSignaturePanel
        token={token}
        firmSettings={firmSettings}
        onReload={load}
        onFirmSettings={setFirmSettings}
        onError={setErr}
      />

      <div className="card" style={{ padding: 12 }}>
        <div className="muted" style={{ marginBottom: 8 }}>
          Universal templates (e.g. <strong>Blank (no precedent)</strong> for letters,{' '}
          <strong>Blank e-mail (no precedent)</strong> for e-mails, <strong>Invoice template</strong>,{' '}
          <strong>Completion statement template</strong>) ship with Canary and are always shown at the top of the
          precedent library below. Edit them in OnlyOffice like any other precedent. Firm-specific letterheads are
          configured in the cards above.
        </div>
        <div className="muted" style={{ marginBottom: 8 }}>
          Upload a template. Choose <strong>Global</strong> at any level to widen availability: <strong>Matter type</strong>{' '}
          Global = all cases; <strong>Sub-type</strong> Global = all sub-types under the chosen matter type;{' '}
          <strong>Precedent category</strong> Global = all categories under the chosen sub-type. Otherwise pick a specific
          value. Add named categories under <strong>Admin → Matters</strong> if you need a specific category.
        </div>
        {uploadCatsFetchErr ? <div className="error" style={{ marginBottom: 8 }}>{uploadCatsFetchErr}</div> : null}
        <div className="stack">
          <label className="field">
            <span>Name (required)</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              aria-required
              placeholder="e.g. Purchase exchange letter"
            />
          </label>
          <label className="field">
            <span>Reference</span>
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                className="mono"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                maxLength={200}
                required
                aria-required
                autoComplete="off"
                spellCheck={false}
                placeholder="e.g. a1f9c2"
                title="Required. Must be unique among precedents."
              />
              <button
                type="button"
                className="btn"
                disabled={busy}
                title="Replace with another random 6-character hex"
                onClick={() => setReference(suggestedPrecedentReferenceHex())}
              >
                New suggestion
              </button>
            </div>
            <span className="muted" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
              Required for every custom precedent. A random 6-character hex is suggested; change it if you prefer. Must be
              unique.
            </span>
          </label>
          <SingleSelectDropdown
            label="Type"
            options={[
              { value: 'letter', label: 'Letter' },
              { value: 'email', label: 'E-mail' },
              { value: 'document', label: 'Document' },
            ]}
            value={kind}
            onChange={(v) => setKind(v as typeof kind)}
          />
          <SingleSelectDropdown
            label="Matter type"
            options={uploadHeadTypeDropdownOptions}
            value={uploadHeadTypeId}
            onChange={(v) => {
              setUploadHeadTypeId(v)
              setUploadSubTypeId('')
              setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
            }}
            disabled={busy}
            placeholder="— select —"
          />
          <SingleSelectDropdown
            label="Sub-type"
            options={uploadSubTypeDropdownOptions}
            value={uploadSubTypeId}
            onChange={(v) => {
              setUploadSubTypeId(v)
              setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
            }}
            disabled={busy || !uploadHeadTypeId || headIsGlobal}
            placeholder="— select —"
          />
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          uploadCatsLoading ? (
            <div className="muted" style={{ fontSize: 13 }}>
              Loading precedent categories…
            </div>
          ) : null}
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          !uploadCatsLoading &&
          !uploadCatsFetchErr &&
          uploadCats.length === 0 ? (
            <div
              className="muted"
              style={{
                fontSize: 13,
                padding: '8px 10px',
                border: '1px solid var(--border)',
                borderRadius: 6,
                background: 'var(--panel)',
              }}
            >
              No named precedent categories exist for this sub-type. You can still choose{' '}
              <strong>Global</strong> above to apply to all categories, or add categories under{' '}
              <strong>Admin → Matters</strong>.
            </div>
          ) : null}
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          !uploadCatsLoading ? (
            <SingleSelectDropdown
              label="Precedent category"
              options={uploadCategoryDropdownOptions}
              value={uploadCategoryId}
              onChange={setUploadCategoryId}
              disabled={busy}
            />
          ) : null}
          <label className="field">
            <span>File</span>
            <input
              key={fileInputKey}
              type="file"
              accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null
                setFile(f)
                if (f && !name.trim()) {
                  setName(precedentDisplayNameFromFile(f))
                }
              }}
            />
          </label>
          {uploadBlockers.length > 0 ? (
            <div className="muted" style={{ fontSize: 13 }}>
              Before uploading: {uploadBlockers.join(' · ')}
            </div>
          ) : null}
          <button
            type="button"
            className="btn primary"
            disabled={busy || !uploadReady}
            onClick={async () => {
              if (!uploadReady || !file) {
                setErr(uploadBlockers[0] ?? 'Complete the form before uploading')
                return
              }
              setBusy(true)
              setErr(null)
              try {
                let mh: string = GLOBAL_PRECEDENT_SCOPE
                let ms: string = GLOBAL_PRECEDENT_SCOPE
                let mc: string = GLOBAL_PRECEDENT_SCOPE
                if (uploadHeadTypeId && uploadHeadTypeId !== GLOBAL_PRECEDENT_SCOPE) {
                  mh = uploadHeadTypeId
                  if (uploadSubTypeId && uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE) {
                    ms = uploadSubTypeId
                    mc = uploadCategoryId || GLOBAL_PRECEDENT_SCOPE
                  } else {
                    ms = GLOBAL_PRECEDENT_SCOPE
                    mc = GLOBAL_PRECEDENT_SCOPE
                  }
                }
                const fd = new FormData()
                fd.set('name', name.trim())
                fd.set('reference', reference.trim())
                fd.set('kind', kind)
                fd.set('matter_head_type_id', mh)
                fd.set('matter_sub_type_id', ms)
                fd.set('category_id', mc)
                fd.set('upload', file)
                if (!String(token ?? '').trim()) {
                  throw new Error('You are not signed in or your session token is empty. Refresh the page and log in again.')
                }
                await apiFetch<PrecedentOut>('/precedents', { token, method: 'POST', body: fd })
                setName('')
                setReference(suggestedPrecedentReferenceHex())
                setFile(null)
                setFileInputKey((k) => k + 1)
                await load()
              } catch (e: unknown) {
                setErr((e as { message?: string }).message ?? 'Upload failed')
              } finally {
                setBusy(false)
              }
            }}
          >
            Upload
          </button>
        </div>
      </div>

      <AdminMergeCodesPanel token={token} onError={setErr} />
      <AdminPrecedentLibraryPanel
        token={token}
        items={items}
        matterHeads={matterHeads}
        busy={busy}
        setBusy={setBusy}
        onReload={load}
        onError={setErr}
      />
    </div>
  )
}
