"""Firm catalogue schema ownership.

Firm-owned catalogue tables live in the Postgres schema ``firm`` (created by
core migrations). ORM models stay schema-unqualified; the DB engine sets
``search_path`` to ``public, firm`` via libpq options and on each pool checkout
(so psycopg3 pool reset does not drop ``firm``).

Core ``public`` keeps users, cases, file metadata, and portal submissions.
System precedent *seed files* ship in the Canary image; their DB rows live in
``firm.precedent`` (kernel-seeded on boot) so detach can clear the catalogue.
"""

from __future__ import annotations

FIRM_CATALOGUE_SCHEMA = "firm"

# Tables owned by the firm catalogue schema (moved by alembic f1r2m3c4t5l6).
FIRM_CATALOGUE_TABLES: tuple[str, ...] = (
    "matter_head_type",
    "matter_sub_type",
    "matter_sub_type_menu",
    "matter_sub_type_standard_task",
    "matter_sub_type_event_template",
    "fee_scale",
    "fee_scale_category",
    "fee_scale_band_set",
    "fee_scale_band_row",
    "fee_scale_line",
    "portal_form_template",
    "portal_form_template_field",
    "precedent_category",
    "precedent",
)
