"""Firm catalogue detach: preflight blockers + force wipe for sandboxes.

Production detach is refused while cases, firm module case_state, or portal
submissions still depend on the firm layer. Force detach requires
``I_CONFIRM_FIRM_DETACH=yes`` (CLI/env) or ``confirm=true`` on the admin API.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.file_storage import FILES_ROOT
from app.firm_catalogue import FIRM_CATALOGUE_SCHEMA
from app.firm_module_runtime import load_manifest, storage_schema
from app.models import Case, File as DbFile, FirmSettings, PortalFormSubmission

log = logging.getLogger(__name__)

_CONFIRM_ENV = "I_CONFIRM_FIRM_DETACH"


@dataclass
class FirmDetachBlockers:
    typed_cases: int = 0
    firm_case_state_rows: int = 0
    portal_submissions: int = 0
    module_schema: str | None = None

    @property
    def blocked(self) -> bool:
        return self.typed_cases > 0 or self.firm_case_state_rows > 0 or self.portal_submissions > 0

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["blocked"] = self.blocked
        return d


@dataclass
class FirmDetachResult:
    ok: bool
    forced: bool = False
    message: str = ""
    blockers: FirmDetachBlockers = field(default_factory=FirmDetachBlockers)
    cleared: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "forced": self.forced,
            "message": self.message,
            "blockers": self.blockers.as_dict(),
            "cleared": dict(self.cleared),
        }


def _confirm_from_env() -> bool:
    return (os.getenv(_CONFIRM_ENV) or "").strip().lower() in ("1", "true", "yes")


def _dialect_name(db: Session) -> str:
    return db.get_bind().dialect.name


def _count_firm_case_state(db: Session) -> tuple[int, str | None]:
    if _dialect_name(db) != "postgresql":
        return 0, None
    schema = storage_schema(load_manifest(force=True))
    if not schema:
        rows = db.execute(
            text(
                """
                SELECT nspname FROM pg_namespace
                WHERE nspname LIKE 'firm_%' AND nspname <> :catalogue
                ORDER BY 1
                """
            ),
            {"catalogue": FIRM_CATALOGUE_SCHEMA},
        ).scalars().all()
        total = 0
        first = None
        for name in rows:
            first = first or name
            exists = db.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = :s AND table_name = 'case_state'
                    )
                    """
                ),
                {"s": name},
            ).scalar()
            if not exists:
                continue
            total += int(
                db.execute(text(f'SELECT count(*) FROM "{name}".case_state')).scalar() or 0
            )
        return total, first
    exists = db.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema = :s AND table_name = 'case_state'
            )
            """
        ),
        {"s": schema},
    ).scalar()
    if not exists:
        return 0, schema
    n = int(db.execute(text(f'SELECT count(*) FROM "{schema}".case_state')).scalar() or 0)
    return n, schema


def collect_detach_blockers(db: Session) -> FirmDetachBlockers:
    typed = int(
        db.execute(
            select(func.count())
            .select_from(Case)
            .where(
                (Case.matter_head_type_id.is_not(None)) | (Case.matter_sub_type_id.is_not(None))
            )
        ).scalar()
        or 0
    )
    case_state_n, module_schema = _count_firm_case_state(db)
    # Submissions for any portal form template (all templates are firm-owned).
    try:
        with db.begin_nested():
            submissions = int(
                db.execute(select(func.count()).select_from(PortalFormSubmission)).scalar() or 0
            )
    except Exception:
        submissions = 0
    return FirmDetachBlockers(
        typed_cases=typed,
        firm_case_state_rows=case_state_n,
        portal_submissions=submissions,
        module_schema=module_schema,
    )


def preflight_detach(db: Session) -> FirmDetachResult:
    blockers = collect_detach_blockers(db)
    if blockers.blocked:
        return FirmDetachResult(
            ok=False,
            message=(
                "Detach blocked: firm layer still has dependents. "
                "Clear or reassign matter types on cases, remove firm module case state, "
                "and void/remove portal submissions — or force-detach in a sandbox."
            ),
            blockers=blockers,
        )
    return FirmDetachResult(
        ok=True,
        message="Detach allowed: no typed cases, firm case_state, or portal submissions.",
        blockers=blockers,
    )


def _unlink_file(db: Session, file_id, cleared: dict[str, int]) -> None:
    if not file_id:
        return
    f = db.get(DbFile, file_id)
    if f is None:
        return
    try:
        path = FILES_ROOT / f.storage_path
        if path.is_file():
            path.unlink()
    except OSError as e:
        log.warning("unlink firm file failed %s: %s", file_id, e)
    db.delete(f)
    cleared["files"] = cleared.get("files", 0) + 1


def _clear_branding(db: Session, cleared: dict[str, int]) -> None:
    firm = db.get(FirmSettings, 1)
    if firm is None:
        return
    brand_ids = [
        firm.letterhead_file_id,
        firm.quote_letterhead_file_id,
        firm.portal_logo_file_id,
        firm.portal_background_file_id,
        firm.default_signature_file_id,
        firm.invoice_template_file_id,
    ]
    firm.trading_name = "Canary"
    firm.registered_company_name = None
    firm.addr_line1 = None
    firm.addr_line2 = None
    firm.town_city = None
    firm.county = None
    firm.postcode = None
    firm.letterhead_file_id = None
    firm.quote_letterhead_file_id = None
    firm.portal_logo_file_id = None
    firm.portal_background_file_id = None
    firm.default_signature_file_id = None
    firm.invoice_template_file_id = None
    firm.portal_background_color = None
    firm.portal_font_color = None
    firm.brand_support_inbox = None
    firm.updated_at = datetime.now(timezone.utc)
    db.add(firm)
    db.flush()
    for fid in brand_ids:
        _unlink_file(db, fid, cleared)
    cleared["branding"] = 1


def _drop_module_schemas(db: Session, cleared: dict[str, int]) -> None:
    if _dialect_name(db) != "postgresql":
        return
    rows = db.execute(
        text(
            """
            SELECT nspname FROM pg_namespace
            WHERE nspname LIKE 'firm_%' AND nspname <> :catalogue
            ORDER BY 1
            """
        ),
        {"catalogue": FIRM_CATALOGUE_SCHEMA},
    ).scalars().all()
    for name in rows:
        db.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        cleared["module_schemas_dropped"] = cleared.get("module_schemas_dropped", 0) + 1
        log.info("Dropped firm module schema %s", name)


def _catalogue_schema_exists(db: Session) -> bool:
    if _dialect_name(db) != "postgresql":
        return False
    return bool(
        db.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = :s)"),
            {"s": FIRM_CATALOGUE_SCHEMA},
        ).scalar()
    )


def _wipe_firm_catalogue(db: Session, cleared: dict[str, int]) -> None:
    """Delete all firm-catalogue rows (schema-aware). Re-seed system precedents on next boot."""
    if not _catalogue_schema_exists(db):
        # Legacy: catalogue still in public — wipe firm-owned public tables.
        _wipe_legacy_public_catalogue(db, cleared)
        return

    # Public dependents of firm catalogue
    if "portal_submissions" not in cleared:
        cleared["portal_submissions"] = db.execute(text("DELETE FROM portal_form_submission")).rowcount or 0
    cleared["fee_scale_favorites"] = db.execute(text("DELETE FROM user_fee_scale_favorite")).rowcount or 0
    cleared["portal_form_fields"] = (
        db.execute(text(f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".portal_form_template_field')).rowcount or 0
    )
    cleared["portal_form_templates"] = (
        db.execute(text(f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".portal_form_template')).rowcount or 0
    )

    for tbl in ("finance_category_template", "billing_line_template"):
        exists = db.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema = 'public' AND table_name = :t
                )
                """
            ),
            {"t": tbl},
        ).scalar()
        if not exists:
            continue
        cols = set(
            db.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :t
                    """
                ),
                {"t": tbl},
            ).scalars()
        )
        if "matter_sub_type_id" in cols:
            db.execute(text(f"DELETE FROM {tbl} WHERE matter_sub_type_id IS NOT NULL"))

    prec_files = list(
        db.execute(
            text(f'SELECT file_id FROM "{FIRM_CATALOGUE_SCHEMA}".precedent WHERE file_id IS NOT NULL')
        ).scalars()
    )

    for stmt, key in (
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".fee_scale_line', "fee_scale_lines"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".fee_scale_band_row', "fee_scale_band_rows"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".fee_scale_band_set', "fee_scale_band_sets"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".fee_scale_category', "fee_scale_categories"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".fee_scale', "fee_scales"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".matter_sub_type_menu', "matter_menus"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".matter_sub_type_event_template', "matter_event_templates"),
        (
            f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".matter_sub_type_standard_task WHERE matter_sub_type_id IS NOT NULL',
            "matter_standard_tasks",
        ),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".precedent', "precedents"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".precedent_category', "precedent_categories"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".matter_sub_type', "matter_sub_types"),
        (f'DELETE FROM "{FIRM_CATALOGUE_SCHEMA}".matter_head_type', "matter_head_types"),
    ):
        try:
            cleared[key] = db.execute(text(stmt)).rowcount or 0
        except Exception as e:
            log.warning("firm catalogue wipe skip %s: %s", key, e)

    for fid in prec_files:
        _unlink_file(db, fid, cleared)


def _safe_delete(db: Session, sql: str, params: dict | None = None) -> int:
    try:
        with db.begin_nested():
            return db.execute(text(sql), params or {}).rowcount or 0
    except Exception as e:
        log.warning("wipe skip %s: %s", sql.split()[1] if sql.split() else sql, e)
        return 0


def _wipe_legacy_public_catalogue(db: Session, cleared: dict[str, int]) -> None:
    """Pre-migration / SQLite-test wipe: firm catalogue tables in the default schema."""
    if "cases_untyped" not in cleared:
        cleared["cases_untyped"] = _safe_delete(
            db,
            """
            UPDATE "case"
            SET matter_head_type_id = NULL, matter_sub_type_id = NULL
            WHERE matter_head_type_id IS NOT NULL OR matter_sub_type_id IS NOT NULL
            """,
        )
    cleared["portal_submissions"] = _safe_delete(db, "DELETE FROM portal_form_submission")
    cleared["portal_form_fields"] = _safe_delete(db, "DELETE FROM portal_form_template_field")
    cleared["portal_form_templates"] = _safe_delete(db, "DELETE FROM portal_form_template")
    cleared["fee_scale_favorites"] = _safe_delete(db, "DELETE FROM user_fee_scale_favorite")
    for stmt, key in (
        ("DELETE FROM fee_scale_line", "fee_scale_lines"),
        ("DELETE FROM fee_scale_band_row", "fee_scale_band_rows"),
        ("DELETE FROM fee_scale_band_set", "fee_scale_band_sets"),
        ("DELETE FROM fee_scale_category", "fee_scale_categories"),
        ("DELETE FROM fee_scale", "fee_scales"),
        ("DELETE FROM matter_sub_type_menu", "matter_menus"),
        ("DELETE FROM matter_sub_type_event_template", "matter_event_templates"),
        (
            "DELETE FROM matter_sub_type_standard_task WHERE matter_sub_type_id IS NOT NULL",
            "matter_standard_tasks",
        ),
        ("DELETE FROM precedent", "precedents"),
        ("DELETE FROM precedent_category", "precedent_categories"),
        ("DELETE FROM matter_sub_type", "matter_sub_types"),
        ("DELETE FROM matter_head_type", "matter_head_types"),
    ):
        cleared[key] = _safe_delete(db, stmt)


def force_detach(db: Session, *, confirm: bool | None = None) -> FirmDetachResult:
    """Wipe firm catalogue + branding + module schemas. Requires confirm."""
    confirmed = _confirm_from_env() if confirm is None else confirm
    blockers = collect_detach_blockers(db)
    if not confirmed:
        return FirmDetachResult(
            ok=False,
            forced=False,
            message=f"Force detach requires {_CONFIRM_ENV}=yes (or confirm=true on the API).",
            blockers=blockers,
        )

    cleared: dict[str, int] = {}
    # Capture stable type names before nulling live FKs (reattach restores from these).
    from app.matter_type_snapshot import capture_snapshots_before_unlink

    cleared["matter_type_snapshots"] = capture_snapshots_before_unlink(db)
    n = db.execute(
        text(
            """
            UPDATE "case"
            SET matter_head_type_id = NULL, matter_sub_type_id = NULL
            WHERE matter_head_type_id IS NOT NULL OR matter_sub_type_id IS NOT NULL
            """
        )
    ).rowcount or 0
    cleared["cases_untyped"] = n

    _wipe_firm_catalogue(db, cleared)
    _clear_branding(db, cleared)
    _drop_module_schemas(db, cleared)
    db.commit()
    log.info("Force firm detach complete: %s", cleared)
    return FirmDetachResult(
        ok=True,
        forced=True,
        message="Firm layer force-detached. Remount the firm package and restart to re-seed.",
        blockers=FirmDetachBlockers(),
        cleared=cleared,
    )


def detach(db: Session, *, force: bool = False, confirm: bool | None = None) -> FirmDetachResult:
    if force:
        return force_detach(db, confirm=confirm)
    result = preflight_detach(db)
    if not result.ok:
        return result
    # Safe detach with no blockers: still wipe empty/unused catalogue so unmount is clean.
    return force_detach(db, confirm=True)


def main() -> None:
    """CLI: ``python -m app.firm_detach [--force]``."""
    import argparse

    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Firm catalogue detach preflight / force wipe")
    parser.add_argument("--force", action="store_true", help=f"Force wipe (requires {_CONFIRM_ENV}=yes)")
    parser.add_argument("--preflight", action="store_true", help="Only report blockers (default)")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.force:
            result = detach(db, force=True)
        else:
            result = preflight_detach(db)
        print(result.as_dict())
        raise SystemExit(0 if result.ok else 2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
