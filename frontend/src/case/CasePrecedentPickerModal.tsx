import { SearchInput } from '../SearchInput'
import type { CaseOut, PrecedentCategoryOut, PrecedentOut } from '../types'

export type CasePrecedentPickerGroup = {
  subId: string
  subName: string
}

export type CasePrecedentPickerModalProps = {
  caseDetail: CaseOut | null
  precedentPickerSubTypeGroups: CasePrecedentPickerGroup[]
  precedentPickerExpandedSubTypes: Set<string>
  precedentCategoriesBySubType: Record<string, PrecedentCategoryOut[]>
  togglePrecedentPickerSubTypeExpanded: (subTypeId: string) => void
  selectPrecedentPickerNav: (subTypeId: string, categoryId: string | null) => void
  precedentPickerSubTypeId: string | null
  precedentPickerCategoryId: string | null
  precedentSearch: string
  setPrecedentSearch: (v: string) => void
  precedentChosenId: string | null
  setPrecedentChosenId: (v: string | null) => void
  filteredPrecedentChoices: PrecedentOut[]
  onClose: () => void
  onContinue: () => void
}

export function CasePrecedentPickerModal({
  caseDetail,
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
  onClose,
  onContinue,
}: CasePrecedentPickerModalProps) {
  return (
      <div
        className="modalOverlay"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.target === e.currentTarget && onClose()}
      >
        <div className="modal card precedentPickerModal" onClick={(e) => e.stopPropagation()}>
          <div className="paneHead">
            <div>
              <h2 className="precedentPickerTitle">Precedent</h2>
              <div className="muted">Choose a category, then a template — or blank.</div>
              {!caseDetail?.matter_sub_type_id && !caseDetail?.matter_head_type_id ? (
                <div className="muted" style={{ marginTop: 4 }}>
                  This case has no matter type set — only precedents that apply to all cases are available.
                </div>
              ) : null}
            </div>
            <button type="button" className="btn" onClick={() => onClose()}>
              Close
            </button>
          </div>
          <div className="precedentPickerBody">
            <div className="precedentPickerCats">
              <div className="precedentPickerCatsTitle">Category</div>
              <div className="precedentPickerCatList">
                {caseDetail?.matter_sub_type_id ? (
                  precedentPickerSubTypeGroups.map((group) => {
                    const expanded = precedentPickerExpandedSubTypes.has(group.subId)
                    const categories = precedentCategoriesBySubType[group.subId] ?? []
                    const isCurrentCaseSubType = group.subId === caseDetail.matter_sub_type_id
                    return (
                      <div key={group.subId} className="precedentPickerSubTypeGroup">
                        <button
                          type="button"
                          className={`precedentPickerSubTypeToggle${isCurrentCaseSubType ? ' precedentPickerSubTypeToggle--current' : ''}`}
                          aria-expanded={expanded}
                          onClick={() => togglePrecedentPickerSubTypeExpanded(group.subId)}
                        >
                          <span className="precedentPickerSubTypeChevron" aria-hidden>
                            {expanded ? '▾' : '▸'}
                          </span>
                          <span>{group.subName}</span>
                        </button>
                        {expanded ? (
                          <div className="precedentPickerSubTypeCategories">
                            <button
                              type="button"
                              className={`precedentPickerCatBtn precedentPickerCatBtn--nested${
                                precedentPickerSubTypeId === group.subId &&
                                precedentPickerCategoryId === null
                                  ? ' active'
                                  : ''
                              }`}
                              onClick={() => selectPrecedentPickerNav(group.subId, null)}
                            >
                              All
                            </button>
                            {categories.map((c) => (
                              <button
                                key={c.id}
                                type="button"
                                className={`precedentPickerCatBtn precedentPickerCatBtn--nested${
                                  precedentPickerSubTypeId === group.subId &&
                                  precedentPickerCategoryId === c.id
                                    ? ' active'
                                    : ''
                                }`}
                                onClick={() => selectPrecedentPickerNav(group.subId, c.id)}
                              >
                                {c.name}
                              </button>
                            ))}
                            {categories.length === 0 ? (
                              <div className="muted precedentPickerSubTypeEmpty">
                                No named categories for this sub-type.
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    )
                  })
                ) : caseDetail?.matter_head_type_id ? (
                  <div className="muted" style={{ padding: '8px 0' }}>
                    All templates for {caseDetail.matter_head_type_name ?? 'this matter type'}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="precedentPickerMain">
              <label className="field" style={{ marginBottom: 8 }}>
                <span>Search by name or reference</span>
                <SearchInput
                  placeholder="Search…"
                  value={precedentSearch}
                  onChange={(e) => setPrecedentSearch(e.target.value)}
                  onClear={() => setPrecedentSearch('')}
                  disabled={!caseDetail?.matter_sub_type_id && !caseDetail?.matter_head_type_id}
                  aria-label="Search precedents"
                />
              </label>
              {!caseDetail?.matter_sub_type_id && !caseDetail?.matter_head_type_id ? (
                <div className="muted precedentPickerEmpty">
                  Set a matter type on this case (practice head or sub-type) to use scoped precedents.
                </div>
              ) : (
                <>
                  <div className="precedentPickerTableHead row">
                    <span className="precedentPickerColPick" />
                    <span className="precedentPickerColName">Name</span>
                    <span className="precedentPickerColRef">Reference</span>
                  </div>
                  <div className="precedentPickerTableBody">
                    <label className="precedentPickerRow rowbtn row">
                      <span className="precedentPickerColPick">
                        <input
                          type="radio"
                          name="precedentChoice"
                          checked={precedentChosenId === null}
                          onChange={() => setPrecedentChosenId(null)}
                        />
                      </span>
                      <span className="precedentPickerColName">Blank (no precedent)</span>
                      <span className="precedentPickerColRef muted">—</span>
                    </label>
                    {filteredPrecedentChoices.map((p) => (
                      <label
                        key={p.id}
                        className={`precedentPickerRow rowbtn row ${precedentChosenId === p.id ? 'active' : ''}`}
                      >
                        <span className="precedentPickerColPick">
                          <input
                            type="radio"
                            name="precedentChoice"
                            checked={precedentChosenId === p.id}
                            onChange={() => setPrecedentChosenId(p.id)}
                          />
                        </span>
                        <span className="precedentPickerColName">{p.name}</span>
                        <span className="precedentPickerColRef mono">{p.reference}</span>
                      </label>
                    ))}
                    {filteredPrecedentChoices.length === 0 ? (
                      <div className="muted precedentPickerEmpty">
                        No precedents match this category and search.
                      </div>
                    ) : null}
                  </div>
                </>
              )}
              <div className="row precedentPickerActions">
                <button type="button" className="btn" onClick={() => onClose()}>
                  Cancel
                </button>
                <button type="button" className="btn primary" onClick={() => onContinue()}>
                  Continue
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
  )
}
