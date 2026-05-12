#!/usr/bin/env python3
"""Promote an uploaded precedent to the reserved “Blank (no precedent)” letter template.

The UI row **Blank (no precedent)** still sends ``precedent_id: null`` for letters; the backend
resolves that to the precedent whose ``reference`` is :data:`app.precedent_constants.BLANK_LETTER_PRECEDENT_REFERENCE`.

Run against your DB (Docker example)::

    docker compose exec backend python scripts/set_blank_letter_precedent.py --match 23562352

``--match`` can be precedent **name**, **reference**, or the uploaded **original_filename** (substring).
If several precedents match, this script scores matches (exact name > exact reference > filename stem >
substring) and prefers the **largest** file on disk to avoid picking an empty stray row.

Use ``--precedent-id <uuid>`` to force a specific row when unsure::

    docker compose exec backend python scripts/set_blank_letter_precedent.py --precedent-id <uuid>

List candidates without changing anything::

    docker compose exec backend python scripts/set_blank_letter_precedent.py --match 23562352 --list-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os

from sqlalchemy import select

from app.db import SessionLocal
from app.file_storage import FILES_ROOT
from app.models import File as DbFile
from app.models import Precedent, PrecedentKind
from app.precedent_constants import BLANK_LETTER_PRECEDENT_REFERENCE


def _disk_size(f: DbFile | None) -> int:
    if f is None:
        return 0
    abs_path = (FILES_ROOT / f.storage_path).resolve()
    try:
        if abs_path.is_file():
            return int(abs_path.stat().st_size)
    except OSError:
        pass
    return int(f.size_bytes or 0)


def collect_matches(db, needle: str) -> list[tuple[Precedent, DbFile | None, int, int]]:
    """Return list of (precedent, file, score, disk_size). Higher score is a better name/ref/filename match."""

    needle = needle.strip()
    out: list[tuple[Precedent, DbFile | None, int, int]] = []
    if not needle:
        return out
    rows = db.execute(select(Precedent)).scalars().all()
    for p in rows:
        f = db.get(DbFile, p.file_id)
        oname = (f.original_filename if f else "") or ""
        stem = Path(oname).stem
        score = 0
        if p.name.strip() == needle:
            score = 100
        elif p.reference.strip() == needle:
            score = 95
        elif oname == needle:
            score = 92
        elif stem == needle:
            score = 88
        elif needle.lower() in oname.lower():
            score = 40
        if score <= 0:
            continue
        sz = _disk_size(f)
        out.append((p, f, score, sz))
    out.sort(key=lambda t: (-t[2], -t[3], str(t[0].id)))
    return out


def find_precedent_match(db, needle: str) -> Precedent | None:
    ranked = collect_matches(db, needle)
    return ranked[0][0] if ranked else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Set reserved blank letter precedent (global letter template).")
    ap.add_argument(
        "--match",
        default="",
        help="Precedent name, reference, or filename clue (unless --precedent-id is set)",
    )
    ap.add_argument("--precedent-id", default="", help="Exact precedent UUID (overrides --match)")
    ap.add_argument(
        "--list-only",
        action="store_true",
        help="Print matching precedents and exit (no DB changes)",
    )
    args = ap.parse_args()

    os.environ.setdefault("FILES_ROOT", "/data/files")

    db = SessionLocal()
    try:
        target: Precedent | None = None
        pid = (args.precedent_id or "").strip()
        if pid:
            try:
                import uuid as uuid_mod

                u = uuid_mod.UUID(pid)
            except ValueError:
                print(f"Invalid --precedent-id {pid!r}", file=sys.stderr)
                sys.exit(1)
            target = db.get(Precedent, u)
            if target is None:
                print(f"No precedent with id {pid}", file=sys.stderr)
                sys.exit(1)
        else:
            needle = (args.match or "").strip()
            if not needle:
                print("Provide --match or --precedent-id", file=sys.stderr)
                sys.exit(1)
            ranked = collect_matches(db, needle)
            if args.list_only:
                if not ranked:
                    print(f"No precedents matched {needle!r}")
                    return
                print(f"Candidates for {needle!r} (score ↓, size ↓):\n")
                for p, f, score, sz in ranked[:25]:
                    fn = (f.original_filename if f else "?") or "?"
                    print(f"  id={p.id} score={score} disk≈{sz}b name={p.name!r} ref={p.reference!r} file={fn!r}")
                return
            if not ranked:
                print(f"No precedent matched {needle!r}. Use --list-only to explore.", file=sys.stderr)
                sys.exit(1)
            target = ranked[0][0]
            if len(ranked) > 1 and ranked[0][2] == ranked[1][2] and ranked[0][3] == ranked[1][3]:
                print(
                    "Ambiguous match (same score and size). Pick one explicitly:\n",
                    file=sys.stderr,
                )
                for p, f, score, sz in ranked[:8]:
                    fn = (f.original_filename if f else "?") or "?"
                    print(f"  --precedent-id {p.id}  score={score} size≈{sz} name={p.name!r} file={fn!r}", file=sys.stderr)
                sys.exit(1)

        assert target is not None

        for o in db.execute(
            select(Precedent).where(
                Precedent.reference == BLANK_LETTER_PRECEDENT_REFERENCE,
                Precedent.id != target.id,
            )
        ).scalars():
            o.reference = f"legacy-{o.id.hex[:12]}"

        target.name = "Blank (no precedent)"
        target.reference = BLANK_LETTER_PRECEDENT_REFERENCE
        target.kind = PrecedentKind.letter
        target.matter_head_type_id = None
        target.matter_sub_type_id = None
        target.category_id = None

        db.commit()
        tf = db.get(DbFile, target.file_id)
        ds = _disk_size(tf)
        print(
            f"OK: precedent {target.id} → name={target.name!r} reference={BLANK_LETTER_PRECEDENT_REFERENCE!r} "
            f"(global letter, file ≈ {ds} bytes on disk)"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
