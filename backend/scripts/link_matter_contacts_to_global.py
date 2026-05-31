#!/usr/bin/env python3
"""Create a global Contact for each unlinked CaseContact and link them.

Safe to re-run: skips matter contacts that already reference an existing global contact.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from sqlalchemy import select

from app.contact_validation import ensure_organisation_trading_name
from app.db import SessionLocal
from app.models import CaseContact, Contact


def _needs_global_link(db, cc: CaseContact) -> bool:
    if cc.contact_id is None:
        return True
    return db.get(Contact, cc.contact_id) is None


def _case_contact_to_contact(cc: CaseContact) -> Contact:
    return Contact(
        type=cc.type,
        name=cc.name,
        email=cc.email,
        phone=cc.phone,
        title=cc.title,
        first_name=cc.first_name,
        middle_name=cc.middle_name,
        last_name=cc.last_name,
        company_name=cc.company_name,
        trading_name=cc.trading_name,
        address_line1=cc.address_line1,
        address_line2=cc.address_line2,
        city=cc.city,
        county=cc.county,
        postcode=cc.postcode,
        country=cc.country,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write changes")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(select(CaseContact).order_by(CaseContact.created_at.asc())).scalars().all()
        created = 0
        linked = 0
        skipped = 0
        for cc in rows:
            if not _needs_global_link(db, cc):
                skipped += 1
                continue
            contact = _case_contact_to_contact(cc)
            ensure_organisation_trading_name(contact.type, contact.trading_name)
            if args.dry_run:
                print(f"Would link case_contact {cc.id} ({cc.name!r}) on case {cc.case_id}")
                created += 1
                continue
            db.add(contact)
            db.flush()
            cc.contact_id = contact.id
            cc.is_linked_to_master = True
            cc.updated_at = datetime.utcnow()
            db.add(cc)
            created += 1
            linked += 1
            print(f"Linked case_contact {cc.id} ({cc.name!r}) -> contact {contact.id}")
        if args.dry_run:
            print(f"Dry run: {created} matter contact(s) would get global cards; {skipped} already linked.")
            return
        db.commit()
        print(f"Created and linked {linked} global contact(s); skipped {skipped} already linked.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
