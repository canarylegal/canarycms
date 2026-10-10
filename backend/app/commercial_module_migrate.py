"""Apply commercial-package SQL migrations from ``COMMERCIAL_MODULE_DIR/migrations``.

Run before core Alembic. Bookkeeping lives in the commercial storage schema.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import text

from app.commercial_module_runtime import commercial_module_dir, load_manifest, storage_schema
from app.db import SessionLocal

log = logging.getLogger(__name__)

_REV_RE = re.compile(r"^(\d{3})_.+\.sql$")


def migrations_dir() -> Path | None:
    directory = commercial_module_dir()
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
            log.warning("Skipping commercial migration with unexpected name: %s", path.name)
            continue
        found.append((m.group(1), path))
    return found


def run_commercial_migrations() -> int:
    """Apply pending commercial SQL revisions. Returns count applied."""
    from app.commercial_package import commercial_package_allows, evaluate_commercial_package_status

    status = evaluate_commercial_package_status(force=True)
    if status.fault:
        log.error(
            "commercial_module_migrate: refusing — %s",
            status.detail or status.message,
        )
        return 0
    if not commercial_package_allows(force=False):
        log.info("commercial_module_migrate: commercial package not attached — skip")
        return 0
    manifest = load_manifest(force=True)
    versions = migrations_dir()
    if not manifest or versions is None:
        log.info("commercial_module_migrate: no commercial module migrations to apply")
        return 0

    schema = storage_schema(manifest)
    if not schema:
        log.warning("commercial_module_migrate: manifest missing storage.schema — skip")
        return 0
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise RuntimeError(f"Invalid commercial storage.schema: {schema!r}")

    applied = 0
    db = SessionLocal()
    try:
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
            log.info("commercial_module_migrate: applying %s (%s)", rev, path.name)
            db.execute(text(sql))
            db.execute(
                text(
                    f'INSERT INTO "{schema}".schema_migrations (revision) VALUES (:rev)'
                ),
                {"rev": rev},
            )
            db.commit()
            applied += 1
    finally:
        db.close()
    log.info("commercial_module_migrate: applied %s revision(s)", applied)
    return applied


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_commercial_migrations()


if __name__ == "__main__":
    main()
