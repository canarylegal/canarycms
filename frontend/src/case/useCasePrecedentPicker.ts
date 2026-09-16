import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import type { PrecedentPickerState } from '../quoteEmailPrecedent'
import type { CaseOut, MatterHeadTypeOut, PrecedentCategoryOut, PrecedentOut } from '../types'

type UseCasePrecedentPickerArgs = {
  token: string
  caseDetail: CaseOut | null
  matterHeadTypes: MatterHeadTypeOut[]
}

export function useCasePrecedentPicker({
  token,
  caseDetail,
  matterHeadTypes,
}: UseCasePrecedentPickerArgs) {
  const [precedentPicker, setPrecedentPicker] = useState<PrecedentPickerState | null>(null)
  const [precedentChoicesBySubType, setPrecedentChoicesBySubType] = useState<
    Record<string, PrecedentOut[]>
  >({})
  const [precedentCategoriesBySubType, setPrecedentCategoriesBySubType] = useState<
    Record<string, PrecedentCategoryOut[]>
  >({})
  const [precedentPickerSubTypeId, setPrecedentPickerSubTypeId] = useState<string | null>(null)
  const [precedentPickerCategoryId, setPrecedentPickerCategoryId] = useState<string | null>(null)
  const [precedentPickerExpandedSubTypes, setPrecedentPickerExpandedSubTypes] = useState<Set<string>>(
    () => new Set(),
  )
  const [precedentSearch, setPrecedentSearch] = useState('')
  const [precedentChosenId, setPrecedentChosenId] = useState<string | null>(null)

  useEffect(() => {
    if (!precedentPicker) {
      setPrecedentChoicesBySubType({})
      setPrecedentCategoriesBySubType({})
      setPrecedentPickerSubTypeId(null)
      setPrecedentPickerCategoryId(null)
      setPrecedentPickerExpandedSubTypes(new Set())
      setPrecedentSearch('')
      return
    }
    const subId = caseDetail?.matter_sub_type_id
    const headOnlyId = caseDetail?.matter_head_type_id
    const kind = precedentPicker.kind
    const preferReference = precedentPicker.preferPrecedentReference
    let cancelled = false
    async function load() {
      try {
        if (!subId) {
          if (headOnlyId) {
            const list = await apiFetch<PrecedentOut[]>(
              `/precedents?kind=${kind}&matter_head_type_id=${headOnlyId}`,
              { token },
            )
            if (cancelled) return
            setPrecedentCategoriesBySubType({})
            setPrecedentChoicesBySubType({ __head__: list })
            setPrecedentPickerSubTypeId('__head__')
            setPrecedentChosenId(
              preferReference ? list.find((p) => p.reference === preferReference)?.id ?? null : null,
            )
            setPrecedentSearch('')
            setPrecedentPickerCategoryId(null)
            setPrecedentPickerExpandedSubTypes(new Set())
            return
          }
          const list = await apiFetch<PrecedentOut[]>(
            `/precedents?kind=${kind}&global_precedents_only=true`,
            { token },
          )
          if (cancelled) return
          setPrecedentCategoriesBySubType({})
          setPrecedentChoicesBySubType({ __global__: list })
          setPrecedentPickerSubTypeId('__global__')
          setPrecedentChosenId(
            preferReference ? list.find((p) => p.reference === preferReference)?.id ?? null : null,
          )
          setPrecedentSearch('')
          setPrecedentPickerCategoryId(null)
          setPrecedentPickerExpandedSubTypes(new Set())
          return
        }

        const headId = caseDetail?.matter_head_type_id
        const head = headId ? matterHeadTypes.find((h) => h.id === headId) : null
        const subGroups =
          head && head.sub_types.length > 0
            ? head.sub_types.map((s) => ({ subId: s.id, subName: s.name }))
            : [{ subId: subId, subName: caseDetail?.matter_sub_type_name ?? 'This sub-type' }]

        const catEntries = await Promise.all(
          subGroups.map(async (g) => {
            const cats = await apiFetch<PrecedentCategoryOut[]>(
              `/matter-types/sub-types/${g.subId}/precedent-categories`,
              { token },
            )
            return [g.subId, cats] as const
          }),
        )
        const list = await apiFetch<PrecedentOut[]>(
          `/precedents?kind=${kind}&matter_sub_type_id=${subId}`,
          { token },
        )
        if (cancelled) return
        setPrecedentCategoriesBySubType(Object.fromEntries(catEntries))
        setPrecedentChoicesBySubType({ [subId]: list })
        setPrecedentPickerSubTypeId(subId)
        setPrecedentPickerCategoryId(null)
        setPrecedentPickerExpandedSubTypes(new Set([subId]))
        setPrecedentChosenId(
          preferReference ? list.find((p) => p.reference === preferReference)?.id ?? null : null,
        )
        setPrecedentSearch('')
      } catch {
        if (!cancelled) {
          setPrecedentCategoriesBySubType({})
          setPrecedentChoicesBySubType({})
          setPrecedentPickerSubTypeId(null)
          setPrecedentPickerCategoryId(null)
          setPrecedentPickerExpandedSubTypes(new Set())
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [
    precedentPicker,
    token,
    caseDetail?.matter_sub_type_id,
    caseDetail?.matter_head_type_id,
    caseDetail?.matter_sub_type_name,
    caseDetail?.id,
    matterHeadTypes,
  ])

  const precedentPickerSubTypeGroups = useMemo(() => {
    const caseSubId = caseDetail?.matter_sub_type_id
    const headId = caseDetail?.matter_head_type_id
    if (!caseSubId) return []
    const head = headId ? matterHeadTypes.find((h) => h.id === headId) : null
    if (head && head.sub_types.length > 0) {
      return head.sub_types.map((s) => ({ subId: s.id, subName: s.name }))
    }
    return [{ subId: caseSubId, subName: caseDetail?.matter_sub_type_name ?? 'This sub-type' }]
  }, [
    matterHeadTypes,
    caseDetail?.matter_head_type_id,
    caseDetail?.matter_sub_type_id,
    caseDetail?.matter_sub_type_name,
  ])

  async function ensurePrecedentChoicesForSubType(subTypeId: string) {
    if (!precedentPicker || precedentChoicesBySubType[subTypeId]) return
    const kind = precedentPicker.kind
    try {
      const list = await apiFetch<PrecedentOut[]>(
        `/precedents?kind=${kind}&matter_sub_type_id=${subTypeId}`,
        { token },
      )
      setPrecedentChoicesBySubType((prev) => ({ ...prev, [subTypeId]: list }))
    } catch {
      setPrecedentChoicesBySubType((prev) => ({ ...prev, [subTypeId]: [] }))
    }
  }

  function togglePrecedentPickerSubTypeExpanded(subTypeId: string) {
    setPrecedentPickerExpandedSubTypes((prev) => {
      const opening = !prev.has(subTypeId)
      if (opening) void ensurePrecedentChoicesForSubType(subTypeId)
      const next = new Set(prev)
      if (next.has(subTypeId)) next.delete(subTypeId)
      else next.add(subTypeId)
      return next
    })
  }

  function selectPrecedentPickerNav(subTypeId: string, categoryId: string | null) {
    setPrecedentPickerSubTypeId(subTypeId)
    setPrecedentPickerCategoryId(categoryId)
    setPrecedentChosenId(null)
    setPrecedentPickerExpandedSubTypes((prev) => new Set(prev).add(subTypeId))
    void ensurePrecedentChoicesForSubType(subTypeId)
  }

  const filteredPrecedentChoices = useMemo(() => {
    const headOnly =
      !!caseDetail && !caseDetail.matter_sub_type_id && !!caseDetail.matter_head_type_id
    const globalOnly = !!caseDetail && !caseDetail.matter_sub_type_id && !caseDetail.matter_head_type_id
    const filterBySearch = (rows: PrecedentOut[]) => {
      const s = precedentSearch.trim().toLowerCase()
      if (!s) return rows
      return rows.filter(
        (p) => p.name.toLowerCase().includes(s) || p.reference.toLowerCase().includes(s),
      )
    }
    if (headOnly) {
      return filterBySearch(precedentChoicesBySubType.__head__ ?? [])
    }
    if (globalOnly) {
      return filterBySearch(precedentChoicesBySubType.__global__ ?? [])
    }
    const activeSubId = precedentPickerSubTypeId ?? caseDetail?.matter_sub_type_id
    if (!activeSubId) return []
    const rows = precedentChoicesBySubType[activeSubId] ?? []
    const cats = precedentCategoriesBySubType[activeSubId] ?? []
    if (cats.length === 0 || precedentPickerCategoryId === null) {
      return filterBySearch(rows)
    }
    const base = rows.filter((p) => !p.category_id || p.category_id === precedentPickerCategoryId)
    return filterBySearch(base)
  }, [
    precedentChoicesBySubType,
    precedentCategoriesBySubType,
    precedentPickerSubTypeId,
    precedentPickerCategoryId,
    precedentSearch,
    caseDetail?.matter_sub_type_id,
    caseDetail?.matter_head_type_id,
  ])

  return {
    precedentPicker,
    setPrecedentPicker,
    precedentPickerSubTypeGroups,
    precedentPickerExpandedSubTypes,
    precedentCategoriesBySubType,
    togglePrecedentPickerSubTypeExpanded,
    selectPrecedentPickerNav,
    precedentPickerSubTypeId,
    precedentPickerCategoryId,
    precedentSearch,
    setPrecedentSearch,
    precedentChosenId,
    setPrecedentChosenId,
    filteredPrecedentChoices,
  }
}
