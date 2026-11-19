# Responsive list columns

Matter/quote, task (including within a matter), contact and audit lists use
proportional grid tracks with minimum widths. Document, DocuSign and portal
summary lists also use proportional tracks. Matter portal tables use flexible
tracks; ledger tables already use percentage columns and a minimum table width.
Document metadata is capped at 96px (Size), 180px (Created) and 100px (User);
Description takes the remaining space on wide screens.
Column order, sorting, double-click opening and right-click menus are unchanged.

Existing `main_menu_column_widths`, `tasks_menu_column_widths` and
`contacts_column_widths` arrays remain in the same preference fields. Their
numbers now act as relative weights: `[100, 200, ...]` gives the second column
twice the first column's space until a minimum is reached. The existing handling
of historical auto-filled defaults is retained. There is no migration or write
on load, container resize, sidebar toggle or viewport change.

Existing divider handles redistribute space between neighbouring columns, using
their current rendered widths. Both columns stop at their minimum. A completed
drag saves one integer weight array through the existing preference mechanism;
clicking a divider without moving it does not save. Losing window focus completes
the drag; reset or component unmount cancels it and removes document listeners.
Audit resizing remains local to the mounted view, as before.

If the available space cannot fit the minimum widths, the table scrolls
horizontally. Headers and rows share the same minimum total width. Minimums are
layout constraints, not replacement preferences: expanding the view restores the
saved proportions. Document lists retain their existing sorting controls; this
change does not add new divider controls where there were none.

## Verification

- `frontend/src/useColumnWidths.test.tsx`: preference preservation, measured
  drag geometry, adjacent-column minimums, one save per drag, click/no-op,
  external preference updates, reset and unmount cleanup.
- `frontend/e2e/column-sizing.spec.ts`: actual browser layout at multiple viewport
  sizes, sidebar toggles, saved preference API checks, drag/reload, header/body
  alignment, menu lists and matter documents.
- `make test-core-workflows` runs these browser checks in the disposable stack
  together with the existing document and session recovery workflows.
