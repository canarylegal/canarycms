"""Apply firm-package SQL migrations from ``FIRM_MODULE_DIR/migrations``.

Firm packages own their revision files; Canary provides this documented entrypoint.
Run **before** core Alembic revisions that drop legacy ``public.firm_module_case_state``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.firm_module_runtime import firm_module_dir, load_manifest, storage_schema

log = logging.getLogger(__name__)

_REV_RE = re.compile(r"^(\d{3})_.+\.sql$")


def migrations_dir() -> Path | None:
    directory = firm_module_dir()
    if directory is None:
        return None
    path = directory / "migrations" / "versions"
    return path if path.is_dir() else None


def _list_revisions(versions: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for path in sorted(versions.iterdir()):
        if not path.is_file() or path.suffix != ".sql":
            continue
        m = _REV_RE.match(path.name)
        if not m:
            log.warning("Skipping firm migration with unexpected name: %s", path.name)
            continue
        found.append((m.group(1), path))
    return found


def run_firm_migrations() -> int:
    """Apply pending firm SQL revisions. Returns count applied. No-op if no module."""
    from app.firm_package import evaluate_firm_package_status, firm_package_allows_module

    status = evaluate_firm_package_status(force=True)
    if status.fault:
        log.error(
            "firm_module_migrate: refusing firm migrations — %s",
            status.detail or status.message,
        )
        return 0
    if not firm_package_allows_module(force=False):
        log.info("firm_module_migrate: firm package not compatible — skip")
        return 0
    manifest = load_manifest(force=True)
    versions = migrations_dir()
    if not manifest or versions is None:
        log.info("firm_module_migrate: no firm module migrations to apply")
        return 0

    schema = storage_schema(manifest)
    if not schema:
        log.warning("firm_module_migrate: manifest missing storage.schema — skip")
        return 0
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise RuntimeError(f"Invalid firm storage.schema: {schema!r}")

    applied = 0
    db = SessionLocal()
    try:
        # Ensure schema + migrations bookkeeping exist before reading applied set.
        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        db.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS "{schema}".schema_migrations (
                    revision TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        db.commit()

        done = {
            str(r[0])
            for r in db.execute(text(f'SELECT revision FROM "{schema}".schema_migrations')).all()
        }
        for rev, path in _list_revisions(versions):
            if rev in done:
                continue
            sql = path.read_text(encoding="utf-8")
            log.info("firm_module_migrate: applying %s (%s)", rev, path.name)
            # Script may include its own CREATE SCHEMA / bookkeeping; run as one block.
            db.execute(text(sql))
            db.execute(
                text(
                    f'INSERT INTO "{schema}".schema_migrations (revision) VALUES (:rev) '
                    f"ON CONFLICT (revision) DO NOTHING"
                ),
                {"rev": rev},
            )
            db.commit()
            applied += 1
            done.add(rev)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    log.info("firm_module_migrate: applied %s revision(s) schema=%s", applied, schema)
    return applied


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_firm_migrations()


if __name__ == "__main__":
    main()
